#!/usr/bin/env python3
"""Run the warehouse_3d test suite on a fresh throwaway database. Works on Linux and Windows.

Run it with the Python of your Odoo 19 virtualenv:

    <venv python> run_tests.py                      # everything (Python, JavaScript/Hoot, tours)
    <venv python> run_tests.py /warehouse_3d:TestRackRow
    <venv python> run_tests.py wh3d_screenshot      # opt-in screenshots

Paths come from environment variables, defaulting to the original Fedora setup:
    WH3D_ODOO_BIN  path to odoo-bin                       (default /mnt/CODE/Workspace/odoo/odoo19/odoo-bin)
    WH3D_CONF      Odoo config with db_host/db_user/...   (default /mnt/CODE/Workspace/odoo/odoo19.conf)
    WH3D_TEST_DB   throwaway database name, DROPPED first; must start with wh3d_test (default wh3d_test)
    WH3D_PORT      HTTP port for browser tests            (default 8079)

Exit status 0 only if tests ran and none failed, errored or were skipped for lack of a browser.
"""
import configparser
import os
import re
import subprocess
import sys

ODOO_BIN = os.environ.get("WH3D_ODOO_BIN", "/mnt/CODE/Workspace/odoo/odoo19/odoo-bin")
CONF = os.environ.get("WH3D_CONF", "/mnt/CODE/Workspace/odoo/odoo19.conf")
DB = os.environ.get("WH3D_TEST_DB", "wh3d_test")
PORT = os.environ.get("WH3D_PORT", "8079")

# Odoo's own SkipTest texts (odoo/tests/common.py): browser tests silently skip without these tools.
BROWSER_SKIPPED = re.compile(r"websocket-client module is not installed|Chrome executable not found|"
                             r"chrome devtools|Chrome headless connection|Error during Chrome connection")
SUMMARY = re.compile(r"\d+ failed, \d+ error\(s\) of (\d+) tests")


def fail(message):
    sys.stdout.flush()  # so the verdict comes after the log, not in the middle of it
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def drop_test_database():
    """DROP the throwaway database (never anything else) using Odoo's own psycopg2."""
    import psycopg2
    from psycopg2 import sql

    if not re.fullmatch(r"wh3d_test[A-Za-z0-9_]*", DB):  # never a real database by mistake
        fail(f"refusing to drop database {DB!r}: test database names must start with wh3d_test")
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(CONF):
        fail(f"Odoo config not found: {CONF} (set WH3D_CONF)")
    options = parser["options"]
    connection = psycopg2.connect(
        dbname="postgres", host=options.get("db_host") or None, port=options.get("db_port") or None,
        user=options.get("db_user") or None, password=options.get("db_password") or None)
    connection.autocommit = True  # DROP DATABASE can't run inside a transaction
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(DB)))
    connection.close()


def main():
    tags = sys.argv[1] if len(sys.argv) > 1 else "/warehouse_3d"
    if not os.path.isfile(ODOO_BIN):
        fail(f"odoo-bin not found: {ODOO_BIN} (set WH3D_ODOO_BIN)")
    drop_test_database()

    command = [sys.executable, ODOO_BIN, "-c", CONF, "-d", DB, "--with-demo", "--http-port", PORT,
               "-i", "warehouse_3d", "--test-tags", tags, "--stop-after-init"]
    lines = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace") as process:
        for line in process.stdout:  # show the log live and keep it for the checks below
            sys.stdout.write(line)
            lines.append(line)
    log = "".join(lines)

    if BROWSER_SKIPPED.search(log):
        fail("browser tests were skipped (install websocket-client in the venv, and Chrome)")
    if "demo data failed to install" in log:
        fail("demo data failed to install (see the traceback above)")
    if re.search(r" (ERROR|CRITICAL) ", log):
        fail("errors in log")
    if process.returncode != 0:
        fail(f"Odoo exited with status {process.returncode}")
    summaries = SUMMARY.findall(log)
    if not summaries or summaries[-1] == "0":
        fail(f"no tests ran (check the test tag: {tags})")
    print([line.strip() for line in lines if SUMMARY.search(line)][-1])
    print("OK")


if __name__ == "__main__":
    main()
