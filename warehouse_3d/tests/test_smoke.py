from odoo.tests import HttpCase, TransactionCase, tagged


class TestSmoke(TransactionCase):

    def test_module_installed(self):
        module = self.env['ir.module.module'].search([('name', '=', 'warehouse_3d')])
        self.assertEqual(module.state, 'installed')


@tagged('post_install', '-at_install')
class TestSmokeTour(HttpCase):

    def test_inventory_opens(self):
        # Proves browser tests really run here (they are skipped silently without websocket-client).
        self.start_tour('/odoo', 'warehouse_3d_smoke', login='admin')
