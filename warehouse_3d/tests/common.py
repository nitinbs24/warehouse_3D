"""Shared test data. Kept small on purpose: each test still says what it needs."""

# The handoff's P05 record (docs/CLAUDE.md): 7 bays × 5 levels × 2 = 70 pallet slots.
P05 = {
    'code': 'P05', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
    'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
}


def create_zone(env, warehouse, name='PR'):
    """An Internal zone location under the warehouse's stock location (rows need one)."""
    return env['stock.location'].create({'name': name, 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})


def create_p05(env, warehouse, zone=None, **overrides):
    """Rack row P05 (and its 113 locations) in ``warehouse``; ``overrides`` change any field."""
    zone = zone or create_zone(env, warehouse)
    return env['warehouse.rack.row'].create(
        dict(P05, warehouse_id=warehouse.id, location_id=zone.id, **overrides))


def template_rows():
    """The handoff's 31 rack faces (docs/CLAUDE.md): P01–P14 pallet, S01–S17 shelving, as field dicts."""
    pallet_x = [0.2, 4.3, 5.6, 9.7, 11.0, 15.1, 16.4, 20.5, 21.8, 25.9, 27.2, 31.3, 32.6, 36.7]
    shelf_x = [round(39.6 + 2.4 * k + d, 1) for k in range(8) for d in (0, 0.6)] + [59.0]
    rows = [dict(P05, code=f'P{i + 1:02d}', x=x) for i, x in enumerate(pallet_x)]
    rows += [{'code': f'S{i + 1:02d}', 'kind': 'shelf', 'x': x, 'y': 2.0, 'bays': 16, 'bay_width': 1.0,
              'depth': 0.6, 'levels': 5, 'level_height': 0.4, 'slots_per_level': 1}
             for i, x in enumerate(shelf_x)]
    return rows
