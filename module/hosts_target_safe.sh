#!/system/bin/sh
# Journaled hosts target writer for normal files and bind-mounted Android hosts.
# A bind-mount cannot be made power-loss atomic by a shell script. A persistent
# preimage and boot-time recovery minimize (but do not eliminate) the risk.
set -eu
umask 077
CMD=${1:-}; TARGET=${2:-}
ROOT=${BH_HOSTS_ROOT:-/data/adb/bindhosts}
case "$CMD" in commit|recover|inspect) : ;; *) echo 'BH_TARGET_ERROR: usage: commit|recover|inspect TARGET [CANDIDATE]' >&2; exit 2 ;; esac
[ "${BH_HOSTS_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || { echo 'BH_TARGET_ERROR: root required' >&2; exit 1; }
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] || { echo 'BH_TARGET_ERROR: unsafe state directory' >&2; exit 1; }
[ -n "$TARGET" ] && [ -f "$TARGET" ] && [ ! -L "$TARGET" ] || { echo 'BH_TARGET_ERROR: unsafe hosts target' >&2; exit 1; }
if [ "${BH_HOSTS_TEST_MODE:-0}" != 1 ]; then
  case "$TARGET" in
    /data/adb/modules/bindhosts/system/etc/hosts|/data/adb/hosts|/data/adb/hostsredirect/hosts|/system/etc/hosts) : ;;
    *) echo 'BH_TARGET_ERROR: unexpected hosts target' >&2; exit 1 ;;
  esac
fi
LOCK="$ROOT/.hosts-target-lock"; JOURNAL="$ROOT/.hosts-target-journal"
LOCKED=0; NEXT=''; COMMITTED=0
fatal() { echo "BH_TARGET_ERROR: $*" >&2; exit 1; }
cleanup() {
  [ -z "$NEXT" ] || rm -f "$NEXT"
  [ "$LOCKED" = 0 ] || rmdir "$LOCK" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
lock() { mkdir "$LOCK" 2>/dev/null || fatal 'another hosts writer is running'; LOCKED=1; }
previous() {
  [ -d "$JOURNAL" ] && [ ! -L "$JOURNAL" ] &&
    [ -f "$JOURNAL/previous" ] && [ ! -L "$JOURNAL/previous" ] &&
    [ -f "$JOURNAL/target" ] && [ ! -L "$JOURNAL/target" ] &&
    [ -f "$JOURNAL/ready" ] && [ ! -L "$JOURNAL/ready" ] || fatal 'unsafe/incomplete journal; manual inspection required'
  [ "$(cat "$JOURNAL/target")" = "$TARGET" ] || fatal 'journal target mismatch'
}
repair() {
  [ -e "$JOURNAL" ] || { echo 'BH_TARGET_RECOVERY_NOT_NEEDED'; return 0; }
  previous
  if cmp -s "$JOURNAL/previous" "$TARGET"; then
    rm -rf "$JOURNAL" || fatal 'cannot remove completed recovery journal'
    echo 'BH_TARGET_ALREADY_RECOVERED'; return 0
  fi
  # Restore original bytes in place; do not attempt renaming a bind mount.
  if ! cat "$JOURNAL/previous" > "$TARGET" || ! cmp -s "$JOURNAL/previous" "$TARGET"; then
    echo 'BH_TARGET_RESTORE_FAILED: persistent previous snapshot retained' >&2
    return 2
  fi
  rm -rf "$JOURNAL" || fatal 'cannot remove recovered journal'
  echo 'BH_TARGET_RECOVERED'; return 0
}
# Inspection must not create a lock, a journal, or any other on-device state.
# It is a genuinely read-only operation, including on a read-only state mount.
if [ "$CMD" = inspect ]; then
  echo "target=$TARGET"
  [ -e "$JOURNAL" ] && echo 'journal=pending' || echo 'journal=clean'
  command -v findmnt >/dev/null 2>&1 && findmnt -T "$TARGET" -n -o TARGET,SOURCE,FSTYPE,OPTIONS || :
  exit 0
fi
lock
if [ "$CMD" = recover ]; then repair; exit $?; fi
[ "$#" -eq 3 ] || fatal 'commit requires candidate path'
CANDIDATE=$3
[ -f "$CANDIDATE" ] && [ ! -L "$CANDIDATE" ] && [ -s "$CANDIDATE" ] || fatal 'candidate missing, symlink or empty'
[ "$(wc -c < "$CANDIDATE")" -le 134217728 ] || fatal 'candidate exceeds 128 MiB'
[ ! -e "$JOURNAL" ] || fatal 'pending recovery journal exists; run recover first'
if cmp -s "$TARGET" "$CANDIDATE"; then echo 'BH_TARGET_UNCHANGED'; exit 0; fi
mkdir "$JOURNAL" || fatal 'cannot create recovery journal'
chmod 0700 "$JOURNAL"
# Fail closed even if creating journal fails; never touch active hosts without snapshot.
cp -p "$TARGET" "$JOURNAL/previous" || fatal 'cannot snapshot active hosts; journal retained'
cmp -s "$TARGET" "$JOURNAL/previous" || fatal 'snapshot mismatch; refusing active write'
printf '%s\n' "$TARGET" > "$JOURNAL/target" || fatal 'cannot record target; journal retained'
cp "$CANDIDATE" "$JOURNAL/next" || fatal 'cannot snapshot candidate; journal retained'
# Durable snapshot before writing the active file. sync is best-effort portability.
sync "$JOURNAL/previous" "$JOURNAL/target" "$JOURNAL/next" 2>/dev/null || sync
# A crash while copying the old bytes must not result in recovery from a
# truncated snapshot. Only a fully checked and synced journal is recoverable.
: > "$JOURNAL/ready" || fatal 'cannot mark completed journal'
sync "$JOURNAL/ready" 2>/dev/null || sync
[ "${BH_HOSTS_FAILPOINT:-}" != after-journal ] || fatal 'injected stop after durable journal'
MODE=$(stat -c %a "$TARGET" 2>/dev/null || echo 644)
OWNER_UID=$(stat -c %u "$TARGET" 2>/dev/null || echo 0)
OWNER_GID=$(stat -c %g "$TARGET" 2>/dev/null || echo 0)
case "$MODE" in ''|*[!0-7]*) MODE=644 ;; esac
NEXT="${TARGET}.bh-next.$$"
if cp "$CANDIDATE" "$NEXT" 2>/dev/null; then
  chmod "$MODE" "$NEXT" 2>/dev/null || :
  chown "$OWNER_UID:$OWNER_GID" "$NEXT" 2>/dev/null || :
  if [ "${BH_HOSTS_FORCE_INPLACE:-0}" != 1 ] && mv -f "$NEXT" "$TARGET" 2>/dev/null; then
    NEXT=''; COMMITTED=1
    command -v restorecon >/dev/null 2>&1 && restorecon "$TARGET" >/dev/null 2>&1 || :
    echo 'BH_TARGET_ATOMIC_PASS'
  fi
fi
if [ "$COMMITTED" = 0 ]; then
  [ -z "$NEXT" ] || { rm -f "$NEXT"; NEXT=''; }
  echo 'BH_TARGET_BIND_FALLBACK: verified in-place write with retained crash journal' >&2
  if [ "${BH_HOSTS_TEST_MODE:-0}" = 1 ]; then
    if [ "${BH_HOSTS_FAILPOINT:-}" = before-inplace ]; then fatal 'injected stop before in-place write'; fi
    if [ "${BH_HOSTS_FAILPOINT:-}" = partial-inplace ]; then
      head -c 8 "$CANDIDATE" > "$TARGET" || :
      fatal 'injected crash after partial bound-hosts write'
    fi
  fi
  if cat "$CANDIDATE" > "$TARGET" && cmp -s "$CANDIDATE" "$TARGET"; then
    COMMITTED=1
    echo 'BH_TARGET_INPLACE_VERIFIED_PASS'
  fi
fi
if [ "$COMMITTED" = 0 ]; then
  repair || exit 2
  fatal 'target write rejected; previous bytes restored'
fi
sync "$TARGET" 2>/dev/null || sync
rm -rf "$JOURNAL" || fatal 'commit succeeded but journal cleanup failed; recover on boot'
echo 'BH_TARGET_COMMIT_PASS'
