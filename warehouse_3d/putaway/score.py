"""Soft rules: which of the allowed slots is best? (docs/todo.md T27)

Pure Python, no ORM. ``stock.putaway.rule._wh3d_rank_slots`` builds the dicts.

product:   {'abc': 'A' | 'B' | 'C' | None, 'heavy': bool (> rules.HEAVY_KG per unit), 'fragile': bool}
candidate: {'dispatch': metres to the nearest dispatch dock, 'z': height of the slot's middle above the floor (m),
            'has_product': the product is already there, 'free_m3': volume left over after putting the goods in}
"""
import math

from .rules import HEAVY_KG  # noqa: F401  (the heavy threshold lives with the hard rules; re-exported for callers)

# AHP weights (docs/review/ahp.py, one respondent, CR < 0.1). Order = CRITERIA.
CRITERIA = ('travel', 'height', 'consolidation', 'waste')
WEIGHTS = (0.53, 0.20, 0.18, 0.09)
BENEFIT = (False, False, True, False)  # only "same product already there" is a benefit

# How much a product cares about distance to dispatch. Not applied to the distance itself: TOPSIS's vector
# normalisation divides a constant factor out again. It scales the travel *weight* (see weights_for).
ABC_FACTOR = {'A': 1.0, 'B': 0.6, 'C': 0.3}
# shortcut: a product without a class is treated as C (slow: it must not take the prime slots by default);
# classify it, or change this, if unclassified goods are mostly fast movers.
DEFAULT_ABC = 'C'
WAIST_Z = 1.1  # m, middle of the comfortable pick zone (about 0.7–1.5 m)


def weights_for(abc):
    """AHP weights with the travel weight scaled by the class factor, renormalised to sum to 1."""
    w = list(WEIGHTS)
    w[0] *= ABC_FACTOR[abc or DEFAULT_ABC]
    total = sum(w)
    return tuple(x / total for x in w)


def height_cost(product, z):
    """0 = ideal. Heavy goods: lower is better (floor first). A-class or fragile: closest to waist height. Else neutral."""
    if product['heavy']:
        return z
    if product['abc'] == 'A' or product['fragile']:
        return abs(z - WAIST_Z)
    return 0.0


def criteria_row(product, candidate):
    return (candidate['dispatch'], height_cost(product, candidate['z']),
            1.0 if candidate['has_product'] else 0.0, candidate['free_m3'])


def topsis(matrix, weights, benefit, minmax=False):
    """Closeness to the ideal solution (0..1, higher is better) per row; Hwang & Yoon (1981).

    Normalise each column, weight it, then compare with the best and worst value per column. The textbook
    normalisation divides by the column's vector norm; ``minmax=True`` rescales each column to 0..1 instead
    (see score()). A column whose values are all equal separates nothing and contributes nothing (no
    division by zero).
    """
    cols = list(zip(*matrix))
    if minmax:
        lows = [min(col) for col in cols]
        norms = [(max(col) - lo) or 1.0 for col, lo in zip(cols, lows)]
    else:
        lows = [0.0] * len(cols)
        norms = [math.sqrt(sum(x * x for x in col)) or 1.0 for col in cols]
    v = [[w * (x - lo) / n for x, w, n, lo in zip(row, weights, norms, lows)] for row in matrix]
    best = [(max if b else min)(col) for col, b in zip(zip(*v), benefit)]
    worst = [(min if b else max)(col) for col, b in zip(zip(*v), benefit)]
    result = []
    for row in v:
        d_best = math.dist(row, best)
        d_worst = math.dist(row, worst)
        result.append(d_worst / (d_best + d_worst) if d_best + d_worst else 0.5)  # all rows identical
    return result


def weighted_sum(matrix, weights, benefit):
    """Simple additive weighting (0..1, higher is better): min-max normalise each column, then weight."""
    scores = [0.0] * len(matrix)
    for j, (col, w, b) in enumerate(zip(zip(*matrix), weights, benefit)):
        lo, hi = min(col), max(col)
        if hi == lo:
            continue  # degenerate column
        for i, x in enumerate(col):
            scores[i] += w * ((x - lo) if b else (hi - x)) / (hi - lo)
    return scores


def score(product, candidates):
    """TOPSIS closeness of each candidate, in order.

    Min-max scaling, not the vector norm: over thousands of slots the norm shrinks a dense column (distance)
    to ~1/sqrt(N) while a sparse one (the product is in one slot) stays at 1, so consolidation would beat
    every weight. Min-max puts "best slot" and "worst slot" at the same scale for every criterion.
    """
    return topsis([criteria_row(product, c) for c in candidates], weights_for(product['abc']), BENEFIT, minmax=True)
