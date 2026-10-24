# Warehaven — `warehouse_3d` for Odoo 19

An Odoo 19 Community add-on that lets you **design a warehouse layout and see it in 3D inside Odoo
Inventory, with live stock**. Rack rows you draw become real Inventory locations; the 3D view shows
those locations with the stock Odoo holds in them, and updates as receipts and deliveries happen.

The working, planning and notes are available within docs.

## What it does

| Where (Inventory menu) | What |
|---|---|
| **Warehouse 3D ▸ 3D View** | Three.js view of the warehouse: racks, shelves, areas, docks, one box per stocked slot. 3D / Top cameras, **Walk** (first person at eye height, WASD + mouse drag), **Colour by occupancy** (green < 50 %, amber 50–90 %, red > 90 %), click or **Find** a slot to see its contents, **Open in Inventory**. Live: stock moved anywhere in Inventory appears without reloading. |
| **Warehouse 3D ▸ Layout Editor** (managers) | Top-down plan. Drag rows (0.1 m snap), edit their sizes, add pallet/shelf rows, delete; overlaps and walls show red at once. **Save** applies everything or nothing. |
| **Configuration ▸ Warehouse 3D ▸ Rack Rows / Layout Areas** | The same data as ordinary Odoo lists and forms. |
| **Configuration ▸ Warehouses ▸ (a warehouse)** | Building length / width / height ("3D Layout"). |
| **Products ▸ (a product) ▸ Inventory tab** | Dimensions L × W × H (m) and ABC class. |

One **rack row** record (code, position, bays, levels, …) generates the 3D geometry *and* its
Inventory locations, e.g. `WHV/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A`. Changing the row renames,
adds or archives its locations — and refuses any change that would remove a location holding stock.

**Template warehouse (demo data):** databases created *with demo data* get *Warehaven DC* (code WHV):
60 × 40 m, 14 pallet rows + 17 shelving rows (980 pallet positions, 1,360 shelf bins), 5 areas,
6 docks, 120 products with dimensions and ABC class, storage categories, Odoo standard putaway rules,
and ~65 % opening stock. It's identical on every machine (fixed random seed).

## Setup

You need: **Odoo 19 Community source**, **Python 3.12** (3.10–3.13 work), **PostgreSQL 16**,
**Google Chrome** (only for running the browser tests), and this repository.
The folder layout below matches the original machine; any layout works if you adjust the paths.

```
<workspace>/
├── odoo19/          Odoo 19 source
├── venv19/          Python virtual environment for Odoo 19
├── odoo19.conf      Odoo config (has your database password: keep it out of git)
└── warehouse_3D/    this repository  (contains the module folder warehouse_3d/)
```

### Fedora Linux (tested)

```bash
# 1. Tools and libraries Odoo's Python packages compile against
sudo dnf install git python3.12 python3.12-devel gcc libpq-devel openldap-devel cyrus-sasl-devel \
                 libxml2-devel libxslt-devel postgresql-server postgresql-contrib

# 2. PostgreSQL: initialise, start, and create a login role for Odoo
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD 'choose-a-password';"
#    Fedora's default only trusts local *system* users ("ident"). Let Odoo log in with the password:
#    in /var/lib/pgsql/data/pg_hba.conf change the "host ... 127.0.0.1/32 ident" line to "scram-sha-256",
#    then: sudo systemctl restart postgresql

# 3. Odoo 19 source and its Python packages
cd <workspace>
git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git odoo19
python3.12 -m venv venv19
venv19/bin/pip install -r odoo19/requirements.txt
venv19/bin/pip install websocket-client          # needed by Odoo's browser tests

# 4. Google Chrome (browser tests only)
sudo dnf install fedora-workstation-repositories
sudo dnf config-manager setopt google-chrome.enabled=1
sudo dnf install google-chrome-stable
```

### Windows 10/11

> **Not yet tried on Windows.** These steps follow Odoo's own Windows support (its `requirements.txt`
> handles Windows); the module itself is plain Python/JavaScript with no OS-specific code. If a step
> fails, note what you did and the error, and fix this section.

1. **Python 3.12** from python.org (64-bit). In the installer tick **"Add python.exe to PATH"**.
2. **PostgreSQL 16** from postgresql.org (EDB installer). Remember the `postgres` password you set.
   Open **SQL Shell (psql)** from the Start menu, log in as `postgres`, and run:
   ```sql
   CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD 'choose-a-password';
   ```
3. **Git for Windows** from git-scm.com, and **Google Chrome** (for the browser tests).
4. In **PowerShell**, in your workspace folder (e.g. `C:\work`):
   ```powershell
   git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git odoo19
   py -3.12 -m venv venv19
   .\venv19\Scripts\python -m pip install -r odoo19\requirements.txt
   .\venv19\Scripts\python -m pip install websocket-client
   ```
   If a package fails to build, install **"Microsoft C++ Build Tools"** (Desktop development with
   C++) and run the `pip install` again.
5. Clone this repository next to `odoo19`.

### The Odoo config file (both systems)

Create `<workspace>/odoo19.conf` (outside the repository — it holds a password):

```ini
[options]
admin_passwd = choose-a-master-password
db_host = 127.0.0.1
db_port = 5432
db_user = odoo
db_password = choose-a-password
http_port = 8069
http_interface = 127.0.0.1
; Odoo's add-ons, then the folder that CONTAINS warehouse_3d (i.e. this repository).
; Windows example: C:\work\odoo19\addons,C:\work\warehouse_3D
addons_path = /path/to/workspace/odoo19/addons,/path/to/workspace/warehouse_3D
```

## Running

```bash
# Fedora (Windows: use venv19\Scripts\python and backslashes)
venv19/bin/python odoo19/odoo-bin -c odoo19.conf -d warehaven_demo --with-demo -i warehouse_3d
```

Open http://127.0.0.1:8069 — a new database's login is `admin` / `admin` (change it under
*My Preferences*). `--with-demo` adds the template warehouse; leave it out for an empty database.

- **After pulling new code**, restart with `-u warehouse_3d` instead of `-i` (install happens once).
- **Demo data is only added at install.** To get a newer template, drop the demo database and
  create it again with the command above.

## Tests

`run_tests.py` creates a throwaway database (`wh3d_test`, **dropped first**), installs the module with
demo data, runs every test — Python, JavaScript (Hoot) and browser tours — and exits non-zero on any
failure, error, skipped browser test, failed demo data, or when no tests ran.

```bash
# Fedora
venv19/bin/python warehouse_3D/run_tests.py                       # everything (~4 min)
venv19/bin/python warehouse_3D/run_tests.py /warehouse_3d:TestRackRow   # one test class
venv19/bin/python warehouse_3D/run_tests.py wh3d_screenshot       # opt-in screenshots → /tmp/odoo_tests/
./warehouse_3D/run_tests.sh                                        # same as the first line
```

```powershell
# Windows (PowerShell): tell the runner where things are, then run it
$env:WH3D_ODOO_BIN = "C:\work\odoo19\odoo-bin"
$env:WH3D_CONF     = "C:\work\odoo19.conf"
.\venv19\Scripts\python warehouse_3D\run_tests.py
```

Other settings: `WH3D_TEST_DB` (default `wh3d_test`; the runner only accepts names starting with
`wh3d_test`, so it can never drop a real database), `WH3D_PORT` (default `8079`, so tests run while
a dev server uses 8069).

Tests that need the template warehouse are skipped, with the reason "needs the demo data", when Odoo
runs the module's tests on a database created without demo data.

## How it is built

```
Browser (OWL components)                                  Server (Python, Odoo ORM)
─────────────────────────                                 ─────────────────────────────────
3D View  view3d_action.js ── wh3d_get_scene ────────────▶ stock.warehouse  (building, scene RPC)
  scene.js     Three.js r128, vendored in static/lib/        │
  layout.js    geometry as plain numbers (tested)           ├─ warehouse.rack.row ──generates──▶ stock.location tree
  occupancy.js fill bands, capacity (tested)                 │    (validation, sync, stock guard, editor save)
  walk.js      walk mode maths (tested)                      ├─ warehouse.layout.area (areas, docks)
  live.js      update queue (tested) ◀── bus message ────────┴─ stock.quant hook: one bus message per transaction
Layout Editor  editor_action.js ── wh3d_get_layout / wh3d_save_layout (all or nothing)
  geometry.js, layout_edit.js (tested; the overlap rule mirrors the server's)
```

| Folder | Contents |
|---|---|
| `warehouse_3d/models/` | Rack rows, layout areas, and Odoo models extended with `_inherit` (location, quant, warehouse, product). |
| `warehouse_3d/static/src/view3d/`, `…/editor/` | The two client actions (OWL + SCSS + XML templates) and their pure helper modules. |
| `warehouse_3d/static/lib/three/` | Three.js r128 + OrbitControls (MIT), loaded only when the 3D view opens. |
| `warehouse_3d/demo/` | The template warehouse: catalogue, products (CSV), layout and opening stock. |
| `warehouse_3d/tests/`, `…/static/tests/` | Python tests, Hoot tests (`*.test.js`) and tours. |
| `docs/` | `plan.md` (decisions), `todo.md` (tasks and how each was verified), `notes.md` (Odoo patterns, task by task), screenshots, the original handoff and prototype. |

## Known limits

- **Putaway is Odoo's standard** ("Closest Location" by storage category). Custom strategies
  (3D bin packing, ABC slotting) are the next plan; the ABC class field is there for them.
- **Fill % is by volume** (product L×W×H × quantity ÷ slot volume), not weight. Products without
  dimensions show "fill unknown".
- **Rack rows are axis-aligned** — no rotated rows.
- **Multi-company:** live-update messages go to every Inventory user; each browser drops other
  warehouses' slots (extra traffic, bare location ids visible across companies).
- **Uninstalling** keeps the generated locations as ordinary locations and leaves Inventory's
  *Storage Locations* setting on. On a **demo** database Odoo also logs an error while removing the
  template warehouse (its routes still point at it) and leaves it in place; real databases uninstall
  cleanly.
- **Windows setup** above is untested so far.
