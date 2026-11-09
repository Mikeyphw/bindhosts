#!/system/bin/sh
# Non-destructive installation smoke test for R2 on rooted Android.
set -eu
MOD=/data/adb/modules/bindhosts/bindhosts.sh
RULES=/data/adb/bindhosts/trackerguard/rules.tsv
DIR=/data/adb/modules/bindhosts

[ "$(id -u)" = 0 ] || { echo 'Run with root: su -c'; exit 2; }
test -f "$DIR/trackerguard_r2.sh" || { echo 'R2 module not installed'; exit 2; }
echo '=== Installed version ==='
grep -E '^(version|versionCode)=' "$DIR/module.prop"
echo '=== Native scanner mode ==='
ABI=$(getprop ro.product.cpu.abi)
test -x "$DIR/bin/$ABI/axmlscan" || { echo 'Native scanner not executable'; exit 2; }
echo "Scanner executable for $ABI"
echo '=== Status and JSON ==='
sh "$MOD" tracker status
sh "$MOD" tracker monitor status
sh "$MOD" tracker json status
sh "$MOD" tracker json rules

echo '=== Check state snapshot without changing IFW ==='
OLD=$(cat "$RULES" 2>/dev/null || true)
sh "$MOD" tracker monitor once
NEW=$(cat "$RULES" 2>/dev/null || true)
[ "$OLD" = "$NEW" ] || { echo 'R2_ACCEPTANCE_UNEXPECTED_RULE_CHANGE'; exit 1; }
echo 'TG_R2_READONLY_ACCEPTANCE_PASS: no existing IFW rules changed'
echo 'Auto-enrollment and package update acceptance still require explicit test.'
