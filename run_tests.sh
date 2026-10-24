#!/usr/bin/env bash
# Run the warehouse_3d test suite on a fresh throwaway database.
# Usage: ./run_tests.sh [test-tags]   e.g. ./run_tests.sh /warehouse_3d:TestLocationGenerator
set -uo pipefail
WS=/mnt/CODE/Workspace/odoo
CONF=$WS/odoo19.conf
DB=wh3d_test
TAGS=${1:-/warehouse_3d}

conf() { sed -n "s/^$1 *= *//p" "$CONF"; }
PGPASSWORD=$(conf db_password) dropdb --if-exists -h "$(conf db_host)" -p "$(conf db_port)" -U "$(conf db_user)" "$DB" || exit 1

LOG=$(mktemp)
# Own port so tests run while a dev server is up on 8069.
"$WS/venv19/bin/python" "$WS/odoo19/odoo-bin" -c "$CONF" -d "$DB" --with-demo --http-port 8079 \
    -i warehouse_3d --test-tags "$TAGS" --stop-after-init 2>&1 | tee "$LOG"
ODOO_STATUS=${PIPESTATUS[0]}

# Browser tests skip silently when websocket-client or Chrome is missing; treat that as a failure.
# Messages are Odoo's own SkipTest texts in odoo/tests/common.py.
if grep -qE "websocket-client module is not installed|Chrome executable not found|chrome devtools|Chrome headless connection|Error during Chrome connection" "$LOG"; then
    echo "FAIL: browser tests were skipped" >&2; exit 1
fi
if grep -qE " (ERROR|CRITICAL) " "$LOG"; then
    echo "FAIL: errors in log" >&2; exit 1
fi
if [ "$ODOO_STATUS" -ne 0 ]; then
    echo "FAIL: Odoo exited with status $ODOO_STATUS" >&2; exit 1
fi
SUMMARY=$(grep -E "[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests" "$LOG" | tail -1)
# A misspelt tag matches nothing and Odoo reports "0 of 0 tests": that's not a pass.
if [ -z "$SUMMARY" ] || echo "$SUMMARY" | grep -qE " of 0 tests"; then
    echo "FAIL: no tests ran (check the test tag: $TAGS)" >&2; exit 1
fi
echo "$SUMMARY"
echo "OK"
