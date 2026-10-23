{
    'name': 'Warehouse 3D',
    'version': '19.0.1.0.0',
    'summary': 'Design a warehouse layout and see it in 3D with live stock',
    'category': 'Supply Chain/Inventory',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/res_groups.xml',
        'views/warehouse_rack_row_views.xml',
        'views/stock_location_views.xml',
        'views/warehouse_layout_area_views.xml',
        'views/product_template_views.xml',
        'views/view3d_actions.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'warehouse_3d/static/src/view3d/**/*',
        ],
        'web.assets_unit_tests': [
            'warehouse_3d/static/tests/*.test.js',
        ],
        'web.assets_tests': [
            'warehouse_3d/static/tests/tours/**/*',
        ],
    },
    'author': 'Warehaven team (VVCE)',
    'license': 'LGPL-3',
    'installable': True,
}
