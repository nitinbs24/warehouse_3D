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
