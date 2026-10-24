from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase


class TestLocationLock(TransactionCase):
    """Locations generated from a rack row can only be renamed or moved through the row."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env.ref('stock.warehouse0')
        cls.stock = warehouse.lot_stock_id
        cls.pr = cls.env['stock.location'].create({'name': 'PR', 'usage': 'internal', 'location_id': cls.stock.id})
        cls.row = cls.env['warehouse.rack.row'].create({
            'code': 'P15', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
            'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
            'warehouse_id': warehouse.id, 'location_id': cls.pr.id,
        })
        Location = cls.env['stock.location']
        cls.slot_1 = Location.search([('name', '=', 'P15-01-1-A'), ('warehouse_id', '=', warehouse.id)])
        cls.slot_7 = Location.search([('name', '=', 'P15-07-1-A'), ('warehouse_id', '=', warehouse.id)])

    def test_renaming_a_generated_location_is_refused(self):
        with self.assertRaisesRegex(UserError, 'P15'):
            self.slot_1.name = 'Somewhere'
        self.assertEqual(self.slot_1.name, 'P15-01-1-A')

    def test_moving_a_generated_location_is_refused(self):
        # This is the exact mistake made in the UI on 23 Oct: a slot moved inside another slot.
        with self.assertRaisesRegex(UserError, 'P15'):
            self.slot_1.location_id = self.slot_7
        self.assertEqual(self.slot_1.complete_name, 'WH/Stock/PR/P15/P15-01/P15-01-1/P15-01-1-A')

    def test_changing_type_of_a_generated_location_is_refused(self):
        with self.assertRaisesRegex(UserError, 'P15'):
            self.slot_1.usage = 'view'

    def test_writing_the_same_values_is_allowed(self):
        self.slot_1.write({'name': 'P15-01-1-A', 'location_id': self.slot_1.location_id.id, 'usage': 'internal'})

    def test_other_fields_stay_editable(self):
        self.slot_1.write({'barcode': 'P15011A', 'cyclic_inventory_frequency': 30})
        self.assertEqual(self.slot_1.barcode, 'P15011A')

    def test_rack_row_changes_still_rename_and_move(self):
        self.row.code = 'P16'
        self.assertEqual(self.slot_1.name, 'P16-01-1-A')

    def test_ordinary_locations_are_not_locked(self):
        self.pr.name = 'Pallet racking'
        self.assertEqual(self.pr.name, 'Pallet racking')

    def test_form_shows_locked_fields_read_only(self):
        form = Form(self.slot_1)
        for field in ('name', 'location_id', 'usage'):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                setattr(form, field, form._values[field])  # Form refuses to set read-only fields
        form.cyclic_inventory_frequency = 30
        form.save()

    def test_form_of_ordinary_location_is_editable(self):
        form = Form(self.pr)
        form.name = 'Pallet racking'
        form.save()
        self.assertEqual(self.pr.name, 'Pallet racking')
