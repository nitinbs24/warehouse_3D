from odoo import Command
from odoo.tests import TransactionCase, new_test_user

from .common import create_p05, create_zone


class TestWarehouseList(TransactionCase):
    """Choosing a warehouse: the list for the dropdown, and the buttons on the warehouse form (T20)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env['stock.warehouse']
        cls.first = cls.env.ref('stock.warehouse0')
        cls.second = cls.Warehouse.create({'name': 'Second', 'code': 'WH2'})

    def _listed(self, warehouses=None):
        warehouses = self.Warehouse if warehouses is None else warehouses  # `or` would swap an empty recordset
        return {w['id']: w for w in warehouses.wh3d_list_warehouses()}

    def test_lists_warehouses_with_their_row_counts(self):
        create_p05(self.env, self.first, create_zone(self.env, self.first))
        create_p05(self.env, self.second, code='P05')
        create_p05(self.env, self.second, code='P06', x=20.5)
        listed = self._listed()
        self.assertEqual(listed[self.first.id], {'id': self.first.id, 'name': self.first.name,
                                                 'code': 'WH', 'row_count': 1})
        self.assertEqual((listed[self.second.id]['name'], listed[self.second.id]['code'],
                          listed[self.second.id]['row_count']), ('Second', 'WH2', 2))

    def test_a_warehouse_without_rows_is_listed_with_zero(self):
        self.assertEqual(self._listed()[self.second.id]['row_count'], 0)

    def test_order_follows_the_warehouse_order(self):
        ids = [w['id'] for w in self.Warehouse.wh3d_list_warehouses()]
        self.assertEqual(ids, self.Warehouse.search([]).ids)

    def test_archived_warehouses_are_left_out(self):
        self.second.active = False
        self.assertNotIn(self.second.id, self._listed())

    def test_other_companies_warehouses_are_left_out_for_users_without_access(self):
        company = self.env['res.company'].create({'name': 'Other Co'})
        foreign = self.Warehouse.search([('company_id', '=', company.id)])
        self.assertTrue(foreign)
        user = new_test_user(self.env, login='wh3d_list_user', groups='stock.group_stock_user',
                             company_id=self.env.company.id, company_ids=[Command.set([self.env.company.id])])
        as_user = self._listed(self.Warehouse.with_user(user))
        self.assertNotIn(foreign.id, as_user)
        self.assertIn(self.first.id, as_user)
        both = self.Warehouse.with_context(allowed_company_ids=[self.env.company.id, company.id])
        self.assertIn(foreign.id, self._listed(both))

    def test_query_count_does_not_grow_with_warehouses_or_rows(self):
        def count_queries():
            self.env.invalidate_all()
            before = self.cr.sql_log_count
            self.Warehouse.wh3d_list_warehouses()
            return self.cr.sql_log_count - before

        base = count_queries()
        self.assertGreater(base, 0, "query counter isn't counting")
        third = self.Warehouse.create({'name': 'Third', 'code': 'WH3'})
        create_p05(self.env, third)
        create_p05(self.env, self.second, code='P06', x=20.5)
        self.assertEqual(count_queries(), base)

    # --- the buttons on the warehouse form

    def test_open_buttons_return_the_client_actions_for_that_warehouse(self):
        for method, tag in (('action_wh3d_open_view3d', 'warehouse_3d.view3d'),
                            ('action_wh3d_open_editor', 'warehouse_3d.editor')):
            with self.subTest(method=method):
                action = getattr(self.second, method)()
                self.assertEqual((action['type'], action['tag']), ('ir.actions.client', tag))
                self.assertEqual(action['context']['warehouse_id'], self.second.id)

    def test_open_buttons_work_on_one_warehouse_at_a_time(self):
        with self.assertRaises(ValueError):
            (self.first | self.second).action_wh3d_open_view3d()

    def test_form_has_the_buttons_and_the_editor_one_is_for_managers(self):
        manager = new_test_user(self.env, login='wh3d_form_manager', groups='stock.group_stock_manager')
        user = new_test_user(self.env, login='wh3d_form_user', groups='stock.group_stock_user')
        manager_arch = self.Warehouse.with_user(manager).get_view(view_type='form')['arch']
        user_arch = self.Warehouse.with_user(user).get_view(view_type='form')['arch']
        for name in ('action_wh3d_open_view3d', 'action_wh3d_open_editor'):
            self.assertIn(name, manager_arch)
        self.assertIn('action_wh3d_open_view3d', user_arch)
        self.assertNotIn('action_wh3d_open_editor', user_arch)
