#!/system/bin/sh
# UX10: Count configured TrackerGuard IFW block rules, not runtime hit events.
# Updates only this module's own module.prop description; fails closed on unsafe files.
set -eu
umask 077
[ "$#" -eq 1 ] && [ "$1" = refresh ] || { echo 'BH_UX10_DESCRIPTION_REFUSED: usage refresh' >&2; exit 2; }
MODDIR=${BH_UX10_MODDIR:-/data/adb/modules/bindhosts}
STATE=${BH_UX10_STATE:-/data/adb/bindhosts}
[ "${BH_UX10_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || exit 1
PROP="$MODDIR/module.prop"
RULES="$STATE/trackerguard/rules.tsv"
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] && [ -f "$PROP" ] && [ ! -L "$PROP" ] || exit 1
[ ! -L "$RULES" ] || exit 1
count=0
if [ -f "$RULES" ]; then
  # Fail on malformed ownership data rather than advertise a misleading count.
  count=$(awk -F'|' '
    NF==3 && $1 ~ /^[A-Za-z0-9_.-]+$/ && $2 ~ /^(receiver|activity|service)$/ && length($3)>0 {n++;next}
    NF==0 || $0=="" {next}
    {bad=1}
    END {if(bad)exit 1; print n+0}
  ' "$RULES") || exit 1
fi
# Serialize updates from boot, Pause/Resume and TrackerGuard monitor/write paths.
LOCK="$MODDIR/.ux10-description.lock"
mkdir "$LOCK" 2>/dev/null || exit 0
TMP=''
cleanup() { [ -z "$TMP" ] || rm -f "$TMP"; rmdir "$LOCK" 2>/dev/null || :; }
trap cleanup EXIT
CURRENT=$(sed -n 's/^description=//p' "$PROP")
[ -n "$CURRENT" ] || exit 1
case "$CURRENT" in
  *' | app trackers blocked: '*) CURRENT=${CURRENT%%' | app trackers blocked: '*} ;;
esac
NEW="$CURRENT | app trackers blocked: $count (configured IFW rules)"
if grep -Fxq "description=$NEW" "$PROP"; then
  printf 'BH_UX10_DESCRIPTION_UNCHANGED count=%s\n' "$count"
  exit 0
fi
TMP=$(mktemp "$MODDIR/.ux10-prop.XXXXXXXX") || exit 1
awk -v new="description=$NEW" '
  /^description=/ {if(replaced++)exit 2; print new;next}
  {print}
  END {if (!replaced) exit 3}
' "$PROP" > "$TMP" || exit 1
chmod 0644 "$TMP"
mv -f "$TMP" "$PROP"
TMP=''
printf 'BH_UX10_DESCRIPTION_PASS count=%s\n' "$count"
