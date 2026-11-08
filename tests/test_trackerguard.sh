#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT INT TERM
mkdir -p "$T/bin" "$T/ifw"
cat > "$T/bin/pm" <<'MOCK'
#!/bin/sh
if [ "$1" = list ] && [ "$2" = packages ] && [ "$3" = -3 ]; then
  printf '%s\n' 'package:com.example.app' 'package:com.other.app'
  exit 0
fi
exit 1
MOCK
chmod +x "$T/bin/pm"
CLI="$ROOT/module/trackerguard.sh"
export TG_STATE_DIR="$T/state" TG_IFW_DIR="$T/ifw" TG_PM="$T/bin/pm" TG_ROOT_SKIP=1
sh "$CLI" status | grep -q 'Explicit blocks: 0'
sh "$CLI" add com.example.app receiver .AnalyticsReceiver
sh "$CLI" add com.example.app service com.sdk.TelemetryService
sh "$CLI" add com.other.app activity .TrackerActivity
RULES="$T/ifw/bindhosts_trackerguard.xml"
grep -q '<broadcast block="true" log="false"><component-filter name="com.example.app/com.example.app.AnalyticsReceiver"/></broadcast>' "$RULES"
grep -q '<service block="true" log="false"><component-filter name="com.example.app/com.sdk.TelemetryService"/></service>' "$RULES"
grep -q '<activity block="true" log="false"><component-filter name="com.other.app/com.other.app.TrackerActivity"/></activity>' "$RULES"
[ "$(grep -c '<component-filter' "$RULES")" -eq 3 ]
python3 - "$RULES" <<'PYXML'
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1]).getroot()
assert r.tag == 'rules'
assert len(r) == 3
assert {c.tag for c in r} == {'service','broadcast','activity'}
PYXML
sh "$CLI" add com.example.app service com.sdk.TelemetryService | grep -q 'already exists'
[ "$(grep -c '<component-filter' "$RULES")" -eq 3 ]
sh "$CLI" remove com.example.app receiver .AnalyticsReceiver
[ "$(grep -c '<component-filter' "$RULES")" -eq 2 ]
sh "$CLI" restore com.example.app
[ "$(grep -c '<component-filter' "$RULES")" -eq 1 ]
sh "$CLI" apply
[ "$(grep -c '<component-filter' "$RULES")" -eq 1 ]
if sh "$CLI" add com.android.settings service .A >/dev/null 2>&1; then echo 'system package accepted' >&2; exit 1; fi
if sh "$CLI" add 'com.example.app"bad' service .A >/dev/null 2>&1; then echo 'XML injection accepted' >&2; exit 1; fi
sh "$CLI" restore --all
[ ! -e "$RULES" ] || { echo 'IFW file not removed' >&2; exit 1; }
printf '<rules><!-- foreign manager --></rules>\n' > "$RULES"
if sh "$CLI" add com.example.app service .A >/dev/null 2>&1; then echo 'foreign file overwritten' >&2; exit 1; fi
grep -q 'foreign manager' "$RULES"
printf 'TG_R0_TESTS_PASS\n'
