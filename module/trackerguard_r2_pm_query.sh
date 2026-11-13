#!/system/bin/sh
# TrackerGuard R3 HF04: read-only Android PackageManager transport adapter.
# No IFW or enrollment writes. Fail closed if no complete snapshot can be obtained.
set -eu
umask 077
[ "$#" -eq 1 ] || { echo 'R2_PM_REFUSED: target argument required' >&2; exit 2; }
TARGET=$1
STATE=${TG_STATE_DIR:-/data/adb/bindhosts/trackerguard}
[ -d "$STATE" ] && [ ! -L "$STATE" ] || { echo 'R2_PM_REFUSED: unsafe private state directory' >&2; exit 2; }
case "$TARGET" in "$STATE"/*) : ;; *) echo 'R2_PM_REFUSED: target outside private state' >&2; exit 2 ;; esac
[ ! -L "$TARGET" ] || { echo 'R2_PM_REFUSED: symlink target' >&2; exit 2; }
# Avoid Termux or root-manager pm/cmd wrappers when the default names are used.
PM_BIN=${TG_PM:-pm}
if [ "$PM_BIN" = pm ] && [ -x /system/bin/pm ]; then PM_BIN=/system/bin/pm; fi
CMD_BIN=${TG_CMD_BIN:-/system/bin/cmd}
if [ ! -x "$CMD_BIN" ] && [ "$CMD_BIN" = /system/bin/cmd ]; then CMD_BIN=cmd; fi
TMP=$(mktemp -d "$STATE/r2pm-hf04.XXXXXXXX") || { echo 'R2_PM_REFUSED: private staging unavailable' >&2; exit 2; }
chmod 700 "$TMP" || { rm -rf "$TMP"; exit 2; }
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Only fixed error classes leave this tool. Never print package identifiers,
# raw command output, stack traces or stderr, even when root commands fail.
errkind() {
  if grep -Eqi 'Failed transaction|Failure calling service|UNKNOWN_TRANSACTION|DeadObjectException' "$1"; then echo binder_transaction
  elif grep -Eqi 'SecurityException|Permission denied|avc: denied' "$1"; then echo permission_or_selinux
  elif grep -Eqi 'Can.t find service|Service not found' "$1"; then echo service_missing
  elif grep -Eqi 'Unknown option|Invalid argument|Usage:' "$1"; then echo unsupported_options
  elif [ -s "$1" ]; then echo other_stderr
  else echo none; fi
}
last_pm=not_run; last_cmd=not_run; attempt=1
while [ "$attempt" -le 3 ]; do
  : > "$TMP/pm.err"
  : > "$TMP/cmd.err"
  if "$PM_BIN" list packages -3 -f --show-versioncode </dev/null > "$TMP/pm.out" 2> "$TMP/pm.err"; then last_pm=0; else last_pm=$?; fi
  if [ "$last_pm" = 0 ] && [ -s "$TMP/pm.out" ]; then
    cp "$TMP/pm.out" "$TARGET" || exit 1
    [ "$attempt" = 1 ] || echo "R2_SNAPSHOT_PM_RECOVERED: attempt=$attempt" >&2
    exit 0
  fi
  if "$CMD_BIN" package list packages -3 -f --show-versioncode </dev/null > "$TMP/cmd.out" 2> "$TMP/cmd.err"; then last_cmd=0; else last_cmd=$?; fi
  if [ "$last_cmd" = 0 ] && [ -s "$TMP/cmd.out" ]; then
    cp "$TMP/cmd.out" "$TARGET" || exit 1
    echo "R2_SNAPSHOT_PM_FALLBACK: using cmd package attempt=$attempt" >&2
    exit 0
  fi
  [ "$attempt" -eq 3 ] || sleep "$attempt"
  attempt=$((attempt + 1))
done
printf 'R2_PM_QUERY_FAILED: attempts=3 pm_rc=%s cmd_rc=%s pm_stderr_class=%s cmd_stderr_class=%s pm_stderr_bytes=%s cmd_stderr_bytes=%s (raw output redacted)\n' \
  "$last_pm" "$last_cmd" "$(errkind "$TMP/pm.err")" "$(errkind "$TMP/cmd.err")" \
  "$(wc -c < "$TMP/pm.err" | tr -d ' ')" "$(wc -c < "$TMP/cmd.err" | tr -d ' ')" >&2
exit 1
