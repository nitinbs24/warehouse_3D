# Learning notes: Odoo patterns, task by task

Each section explains the Odoo ideas a task introduced, the first time they appear.
Read alongside the code of that task's commit (`git log --oneline` in `warehouse_3D/`).

## T0: Environment and an empty module

**Two Odoo versions side by side.** Odoo reads one config file per server process (`-c`).
`odoo.conf` stays the Odoo 18 file; `odoo19.conf` is the Odoo 19 one. They share the PostgreSQL
role `odoo18` but use different databases (`warehaven` for development, `wh3d_test` for tests), so
nothing collides. The dev server is `venv19/bin/python odoo19/odoo-bin -c odoo19.conf`.

**`addons_path`** is the list of folders Odoo scans for modules. Any sub-folder with a
`__manifest__.py` is a module. We added `/mnt/CODE/Workspace/odoo/warehouse_3D`, so
`warehouse_3D/warehouse_3d/` is found; `docs/` is ignored because it has no manifest.

**A module is a Python package plus a manifest.**
- `__manifest__.py` is a plain dict: name, version (`19.0.x.y.z` = Odoo series + module version),
  `depends` (modules that must be installed first — for us only `stock`, which pulls in
  `product`, `web`, etc.), `data` (XML/CSV files loaded on install, in order), `demo` (loaded only
  on databases created with `--with-demo`), and `assets` (JS/CSS/XML added to front-end bundles).
- `__init__.py` imports the Python sub-packages (`models`, later). Empty for now.
- `tests/` is imported by Odoo's test runner only, never in production.

**Asset bundles.** Odoo doesn't serve JS files one by one; it concatenates them into named bundles.
`web.assets_backend` is the main back-office bundle, `web.assets_tests` is only loaded when a test
tour runs. Our tour file goes into `web.assets_tests` so it never ships to real users.

**Two kinds of tests.**
- `TransactionCase`: Python, runs inside a database transaction that is rolled back after each
  test, so tests can't pollute each other. Used for models and business logic. Very fast.
- `HttpCase` + **tour**: starts headless Chrome, logs in, and replays steps written in JS
  (`static/tests/tours/*.js`): "wait for this CSS selector, then click it". Used to prove the UI
  works. Needs the `websocket-client` Python package (Chrome is driven over a websocket). Without
  it Odoo *skips* the test without failing, which is why `run_tests.sh` treats a skip as a failure.
- `@tagged('post_install', '-at_install')` makes a test run after all modules are installed
  instead of right after ours; tours need the full menu and assets, so they always use it.

**Running tests:** `warehouse_3D/run_tests.sh` drops `wh3d_test`, installs the module with demo
data, runs every test tagged `/warehouse_3d`, and exits non-zero on any error, failure or skipped
browser test. Pass a tag to run one class: `./run_tests.sh /warehouse_3d:TestSmoke`. It uses port
8079, so it works while the dev server runs on 8069.
