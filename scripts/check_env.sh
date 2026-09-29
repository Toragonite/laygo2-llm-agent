#!/usr/bin/env bash
# Verify the Phase 0-1 environment. Prints one PASS/FAIL line per check; exit 1 if any fail.
# Run from anywhere: scripts/check_env.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS="$ROOT/third_party/laygo2_workspace_sky130"
: "${PDK_ROOT:=$HOME/pdk}"
export PDK_ROOT
fail=0

check() {  # check <name> <expected-substring> <command...>
  local name="$1" want="$2"; shift 2
  local out; out="$("$@" 2>&1)"
  if grep -qF -- "$want" <<<"$out"; then
    echo "PASS  $name"
  else
    echo "FAIL  $name (expected '$want')"; echo "$out" | tail -5 | sed 's/^/      /'; fail=1
  fi
}

check "submodule laygo2 @ cc6276a" "cc6276a" git -C "$ROOT/third_party/laygo2" rev-parse HEAD
check "submodule workspace @ e7bc4fd" "e7bc4fd" git -C "$WS" rev-parse HEAD
check "laygo2 import (not shadowed)" "third_party/laygo2/laygo2/__init__.py" \
  bash -c "cd '$WS' && PYTHONPATH=. uv run --project '$ROOT' python -c 'import laygo2, laygo2_tech; print(laygo2.__file__)'"
check "magic 8.3.460" "8.3.460" magic --version
check "magic tech sky130A" "TECH=sky130A" \
  bash -c "cd /tmp && echo 'puts TECH=[tech name]; quit -noprompt' | timeout 60 magic -dnull -noconsole -rcfile '$ROOT/flow/maginit.tcl'"
check "netgen-lvs" "Netgen 1.5" netgen-lvs -batch quit
check "ngspice" "ngspice-42" ngspice --version
check "PDK open_pdks 6d4d117" "6d4d117" cat "$PDK_ROOT/sky130A/SOURCES"
check "netgen setup file" "sky130A_setup.tcl" ls "$PDK_ROOT/sky130A/libs.tech/netgen/sky130A_setup.tcl"

exit $fail
