"""Hard rules: may these goods go into this slot? (docs/survey.md A8, docs/todo.md T25)

Plain data in, plain data out, no ORM: ``stock.putaway.rule._wh3d_check_slots`` builds the dicts.

goods:    {'products': [product], 'qty': units of the (single) product, 'purpose': 'normal' | 'quarantine' | …,
           'dest_path': parent_path of the putaway destination, optional 'package': True, 'weight': kg, 'volume': m³}
product:  {'id', 'temp_band', 'temp_min', 'temp_max', 'hazard', 'fragile', 'weight' (kg/unit), 'dims' (l, w, h m)}
slot:     {'id', 'row': {'temp_band', 'temp_min', 'temp_max', 'hazards' (set), 'purpose', 'inspection_status',
           'zone_path'}, 'size' (w, d, h m), 'capacity_m3', 'category' (None or {'max_weight', 'allow_new_product',
           'product_capacity', 'package_capacity'}), 'forecast_weight', 'location_qty', 'above', 'below'}
contents: what the slot holds or will hold: [product + {'qty': on hand + incoming, 'on_hand': on hand}];
          ``above`` / ``below`` are the same for the slot directly above / below.
"""
from collections import namedtuple

HEAVY_KG = 25.0  # per unit; heavier never goes directly above something fragile
EPS = 1e-6

# code: stable key for T28 messages, T29 reasons and T32 violation counts; text: for people.
Reason = namedtuple('Reason', 'code text')


def _volume(item):
    l, w, h = item['dims']
    return l * w * h


def _temperature(goods, slot):
    zone = slot['row']
    for p in goods['products']:
        if p['temp_band'] == 'none':
            continue  # no requirement: any zone, controlled or not
        if zone['temp_band'] == 'ambient':
            return f"needs {p['temp_min']:g}…{p['temp_max']:g} °C; this row is not temperature-controlled"
        if zone['temp_min'] < p['temp_min'] - EPS or zone['temp_max'] > p['temp_max'] + EPS:
            return (f"needs {p['temp_min']:g}…{p['temp_max']:g} °C; this row holds "
                    f"{zone['temp_min']:g}…{zone['temp_max']:g} °C")
    return None


def _hazard(goods, slot, contents):
    classes = {p['hazard'] for p in goods['products']} - {'none'}
    unapproved = classes - slot['row']['hazards']
    if unapproved:
        return f"this row is not approved for {', '.join(sorted(unapproved))}"
    present = {c['hazard'] for c in contents} - {'none'}
    if len(classes | present) > 1:
        return f"one hazard class per slot; it holds {', '.join(sorted(present))}"
    return None


def _purpose(goods, slot):
    zone = slot['row']
    if zone['purpose'] == 'normal':
        return None if goods['purpose'] == 'normal' else f"{goods['purpose']} goods stay out of normal rows"
    # parent_path prefix ("1/7/40/"), not names: "WH/Stock/Q" must not match "WH/Stock/QUAR".
    if not goods['dest_path'].startswith(zone['zone_path']):
        return f"{zone['purpose']} row: only for goods sent into its zone"
    return None


def _fit(goods, slot, contents):
    width, depth, height = slot['size']
    for p in goods['products']:
        l, w, h = p['dims']
        if not (l and w and h):
            continue  # dimensions unknown: can't check (as the 3D view's fill %)
        footprint = (l <= width + EPS and w <= depth + EPS) or (w <= width + EPS and l <= depth + EPS)
        if h > height + EPS or not footprint:
            return f"{l:g} × {w:g} × {h:g} m doesn't fit a {width:g} × {depth:g} × {height:g} m slot"
    incoming = goods.get('volume')
    if incoming is None and not goods.get('package') and len(goods['products']) == 1:
        # Odoo asks with quantity 0 for a new line: check one unit, so a full slot isn't suggested.
        incoming = _volume(goods['products'][0]) * max(goods['qty'], 1) or None
    if incoming is None or not all(_volume(c) for c in contents):
        return None  # some volume unknown: only the per-unit check above applies
    used = sum(_volume(c) * c['qty'] for c in contents)
    if used + incoming > slot['capacity_m3'] + EPS:
        return f"needs {incoming:.2f} m³; {max(0.0, slot['capacity_m3'] - used):.2f} m³ free"
    return None


def _fragile(goods, slot):
    if any(p['fragile'] for p in goods['products']) and any(c['weight'] > HEAVY_KG for c in slot['above']):
        return "fragile goods never go directly below a heavy product"
    if any(p['weight'] > HEAVY_KG for p in goods['products']) and any(c['fragile'] for c in slot['below']):
        return "heavy goods never go directly above a fragile product"
    return None


def _odoo_capacity(goods, slot, contents):
    """stock.location._check_can_be_used, on prepared data (same order and comparisons)."""
    category = slot['category']
    if not category:
        return None
    on_hand = {c['id'] for c in contents if c['on_hand'] > EPS}
    wanted = {p['id'] for p in goods['products']}
    if category['allow_new_product'] == 'empty' and on_hand:
        return "storage category takes new products only when the slot is empty"
    if category['allow_new_product'] == 'same':
        incoming_other = any(c['id'] not in wanted and c['qty'] - c['on_hand'] > EPS for c in contents)
        if len(wanted) > 1 or (on_hand and on_hand != wanted) or incoming_other:
            return "storage category allows one product per slot"
    if goods.get('package'):
        weight = goods.get('weight', 0.0)
        capacity = category['package_capacity']
    else:
        weight = goods['products'][0]['weight'] * goods['qty']
        capacity = category['product_capacity']
    if category['max_weight'] < slot['forecast_weight'] + weight:
        return f"over the {category['max_weight']:g} kg limit"
    location_qty = slot['location_qty']
    if capacity and (location_qty >= capacity or (not goods.get('package') and goods['qty'] + location_qty > capacity)):
        return f"storage category holds at most {capacity:g} here"
    return None


def allowed(goods, slot, contents):
    """(True, None) if every hard rule passes, else (False, Reason) for the first that fails."""
    row = slot['row']
    if row['inspection_status'] != 'green':
        return False, Reason('inspection', f"rack inspection is {row['inspection_status']}: no putaway until repaired")
    checks = (
        ('purpose', lambda: _purpose(goods, slot)),
        ('temperature', lambda: _temperature(goods, slot)),
        ('hazard', lambda: _hazard(goods, slot, contents)),
        ('fit', lambda: _fit(goods, slot, contents)),
        ('fragile', lambda: _fragile(goods, slot)),
        ('odoo_capacity', lambda: _odoo_capacity(goods, slot, contents)),
    )
    for code, check in checks:
        text = check()
        if text:
            return False, Reason(code, text)
    return True, None
