"""Walkable distances from every slot to the docks, with racks as obstacles (docs/todo.md T26, survey A9.3).

The floor is a grid of CELL × CELL squares; a square that overlaps a rack is blocked. Movement is rectilinear
(up/down/left/right), which is how trucks and pickers move along aisles, and every step costs the same, so a
breadth-first search from all docks of a role at once is Dijkstra. A slot is reached at the floor cell next to
its rack face, on whichever side is nearer (a back-to-back side is closed); all levels of a bay position share
that point (vertical travel is ignored, survey A9.1).

Pure Python: plain tuples in, a read-only mapping out, cached on the layout's geometry itself, so an edit made
anywhere (editor, form, import) gives a new key and never a stale answer.
"""
import math
from collections import deque
from functools import lru_cache
from types import MappingProxyType

# shortcut: a 0.5 m grid only guarantees an aisle ≥ 1.0 m wide is walkable (narrower ones depend on how they
# line up with the cells); gaps under 0.5 m are always closed. Template aisles are 1.2 m and 3 m, back-to-back
# gaps 0.2 m. Use a finer grid if layouts with 0.6–1.0 m walkways matter.
CELL = 0.5
EPS = 1e-6
ROLES = {'dispatch': ('outbound', 'both'), 'receiving': ('inbound', 'both')}


def _cells(lo, hi, count):
    """Indices of the cells that overlap the open interval (lo, hi) along one axis."""
    first = max(0, math.floor((lo + EPS) / CELL))
    last = min(count - 1, math.ceil((hi - EPS) / CELL) - 1)
    return range(first, last + 1)


def _bfs(blocked, starts, nx, ny):
    """Steps from the nearest start to every free cell; None where unreachable."""
    steps = [[None] * ny for _ in range(nx)]
    queue = deque()
    for i, j in starts:
        if not blocked[i][j] and steps[i][j] is None:
            steps[i][j] = 0
            queue.append((i, j))
    while queue:
        i, j = queue.popleft()
        for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= a < nx and 0 <= b < ny and not blocked[a][b] and steps[a][b] is None:
                steps[a][b] = steps[i][j] + 1
                queue.append((a, b))
    return steps


@lru_cache(maxsize=8)
def slot_distances(building, rows, docks):
    """{(row id, bay, position): (metres to the nearest dispatch dock, … receiving dock)}.

    building = (length, width); rows = ((id, x, y, depth, bays, bay_width, slots_per_level[, orientation]), …),
    orientation 'y' (default: depth along x, bays along y) or 'x' (bays along x, depth along y);
    docks = ((x, y, width, depth, role), …) with role 'inbound' | 'outbound' | 'both'.
    A distance is None when no dock has that role or the slot can't be reached.
    """
    length, width = building
    # A partial cell at a wall that isn't a multiple of CELL is dropped: a strip under CELL is never walkable.
    nx, ny = math.floor(length / CELL + EPS), math.floor(width / CELL + EPS)
    blocked = [[False] * ny for _ in range(nx)]
    rows = [(*r, 'y') if len(r) == 7 else r for r in rows]
    for _id, x, y, depth, bays, bay_width, _spl, orientation in rows:
        w, h = (bays * bay_width, depth) if orientation == 'x' else (depth, bays * bay_width)
        for i in _cells(x, x + w, nx):
            for j in _cells(y, y + h, ny):
                blocked[i][j] = True

    steps = {}
    for purpose, roles in ROLES.items():
        starts = [(i, j) for dx, dy, dw, dd, role in docks if role in roles
                  for i in _cells(dx, dx + dw, nx) for j in _cells(dy, dy + dd, ny)]
        steps[purpose] = _bfs(blocked, starts, nx, ny) if starts else None

    result = {}
    for row_id, x, y, depth, bays, bay_width, spl, orientation in rows:
        # Across the depth (a, size, count) and along the length (b, count) of the row, in grid axes.
        a, b, across_n, along_n = (y, x, ny, nx) if orientation == 'x' else (x, y, nx, ny)
        # The free cell just outside each rack face: below a, above a + depth.
        faces = [c for c in (math.floor((a + EPS) / CELL) - 1, math.ceil((a + depth - EPS) / CELL)) if 0 <= c < across_n]
        for bay in range(1, bays + 1):
            for pos in range(1, spl + 1):
                # Position A is the lower part of the bay along the row, as slotBox in static/src/view3d/layout.js.
                k = min(along_n - 1, math.floor((b + (bay - 1) * bay_width + (pos - 0.5) * bay_width / spl) / CELL))
                cells = [(k, c) if orientation == 'x' else (c, k) for c in faces]
                pair = []
                for purpose in ROLES:
                    grid = steps[purpose]
                    found = [grid[i][j] for i, j in cells if grid and grid[i][j] is not None]
                    pair.append(min(found) * CELL if found else None)
                result[(row_id, bay, pos)] = tuple(pair)
    return MappingProxyType(result)
