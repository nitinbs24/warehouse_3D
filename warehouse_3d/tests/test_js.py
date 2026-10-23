from odoo.tests import tagged

from odoo.addons.web.tests.test_js import HOOTCommon, unit_test_error_checker


@tagged('post_install', '-at_install')
class TestWarehouse3dHoot(HOOTCommon):
    """Runs this module's Hoot (JavaScript unit) tests: static/tests/*.test.js."""

    def test_hoot_suite(self):
        # Hoot selects a suite by a hash of its name; our tests live in the "@warehouse_3d" suite.
        module_filter = f"&id={self._generate_hash('@warehouse_3d')}"
        self.browser_js(
            f'/web/tests?headless&loglevel=2&preset=desktop&timeout=15000{module_filter}', "", "",
            login='admin', timeout=600, success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )
