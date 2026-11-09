#!/system/bin/sh
# Explicit rooted-device acceptance; read-only unless BOTH live flags are present.
set -eu
MODDIR=${BH_ACCEPT_MODDIR:-/data/adb/modules/bindhosts}
STATE=${BH_ACCEPT_STATE:-/data/adb/bindhosts}
[ "$(id -u)" = 0 ] || { echo 'BH_ACCEPT_REFUSED: root required' >&2; exit 1; }
# Fail closed for typos: a live test requires both exact arguments, never a prefix.
case "$#:${1:-}" in
  0:|1:--read-only) _accept_mode=readonly ;;
  2:--probe-live)
    [ "${2:-}" = --accept-risk ] || { echo 'BH_ACCEPT_REFUSED: --accept-risk required' >&2; exit 2; }
    _accept_mode=live ;;
  *) echo 'BH_ACCEPT_REFUSED: valid options: --read-only OR --probe-live --accept-risk' >&2; exit 2 ;;
esac
[ -f "$MODDIR/mode.sh" ] || { echo 'BH_ACCEPT_REFUSED: installed module mode unavailable' >&2; exit 1; }
# shellcheck disable=SC1090
. "$MODDIR/mode.sh"
case "${operating_mode:-0}" in
  3) TARGET=/data/adb/hosts ;;
  4) TARGET=/data/adb/hostsredirect/hosts ;;
  7|8) TARGET=/system/etc/hosts ;;
  *) TARGET="$MODDIR/system/etc/hosts" ;;
esac
WRITER="$MODDIR/hosts_target_safe.sh"
[ -f "$TARGET" ] && [ ! -L "$TARGET" ] && [ -f "$WRITER" ] || { echo 'BH_ACCEPT_REFUSED: target/writer unavailable' >&2; exit 1; }
printf 'BH_ACCEPT_TARGET=%s\n' "$TARGET"
printf 'BH_ACCEPT_MODE=%s\n' "${operating_mode:-0}"
ls -lZ "$TARGET" 2>/dev/null || ls -l "$TARGET"
command -v findmnt >/dev/null 2>&1 && findmnt -T "$TARGET" -o TARGET,SOURCE,FSTYPE,OPTIONS || :
BH_HOSTS_ROOT="$STATE" sh "$WRITER" inspect "$TARGET"
[ "$_accept_mode" = live ] || { echo 'BH_ACCEPT_READ_ONLY_PASS: no hosts changed'; exit 0; }
# Do not alter live hosts if a previous writer has an unfinished recovery journal.
[ ! -e "$STATE/.hosts-target-journal" ] || { echo 'BH_ACCEPT_REFUSED: pending journal, recover first'; exit 1; }
STAGE=$(mktemp -d "$STATE/.hosts-accept.XXXXXXXX") || exit 1
trap 'rm -rf "$STAGE"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cp -p "$TARGET" "$STAGE/previous" || exit 1
printf '# bindhosts acceptance %s\n' "$$" > "$STAGE/marker"
cat "$STAGE/previous" "$STAGE/marker" > "$STAGE/next" || exit 1
restore() {
  if ! cmp -s "$TARGET" "$STAGE/previous"; then
    if ! BH_HOSTS_ROOT="$STATE" sh "$WRITER" commit "$TARGET" "$STAGE/previous"; then
      echo 'BH_ACCEPT_RESTORE_FAILED: snapshot is retained in pending journal or test staging' >&2
      return 1
    fi
  fi
  cmp -s "$TARGET" "$STAGE/previous"
}
# On error, attempt rollback before stage cleanup. A persistent writer journal
# remains independently recoverable if the process dies mid-write.
trap 'if restore; then rm -rf "$STAGE"; else echo BH_ACCEPT_MANUAL_RECOVERY_REQUIRED_PREIMAGE_RETAINED >&2; fi' EXIT
BH_HOSTS_ROOT="$STATE" sh "$WRITER" commit "$TARGET" "$STAGE/next" || { echo 'BH_ACCEPT_WRITE_REFUSED'; exit 1; }
cmp -s "$TARGET" "$STAGE/next" || { echo 'BH_ACCEPT_WRITE_MISMATCH'; exit 1; }
restore || exit 1
trap 'rm -rf "$STAGE"' EXIT
echo 'BH_ACCEPT_LIVE_ROUNDTRIP_PASS: marker written and original bytes restored'
