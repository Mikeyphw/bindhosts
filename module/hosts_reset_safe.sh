#!/system/bin/sh
# UX03 safe reset/toggle: preserve installed hosts until a complete candidate is ready.
set -eu
umask 077
[ "$#" -eq 4 ] || { echo 'BH_RESET_ERROR: usage reset|toggle TARGET STATE MODDIR' >&2; exit 2; }
ACTION=$1; TARGET=$2; STATE=$3; MODDIR=$4
case "$ACTION" in reset|toggle) : ;; *) exit 2 ;; esac
[ -d "$STATE" ] && [ ! -L "$STATE" ] && [ -f "$TARGET" ] && [ ! -L "$TARGET" ] || exit 1
WRITER="$MODDIR/hosts_target_safe.sh"
PARSE="$MODDIR/hosts_update_parse.awk"
[ -f "$WRITER" ] && [ -f "$PARSE" ] || exit 1
export BH_HOSTS_ROOT="$STATE"
BACKUP="$STATE/bindhosts_backup"
STAGE=$(mktemp -d "$STATE/.hosts-reset.XXXXXXXX") || exit 1
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Never overwrite/remove another program's backup or a symlink.
[ ! -L "$BACKUP" ] || { echo 'BH_RESET_ERROR: unsafe prior backup' >&2; exit 1; }
if [ "$ACTION" = toggle ] && [ -f "$BACKUP" ]; then
  sh "$WRITER" commit "$TARGET" "$BACKUP" || exit 1
  rm -f "$BACKUP" || exit 1
  echo 'BH_RESET_RESTORED_PASS'
  exit 0
fi
{
  printf '127.0.0.1 localhost\n::1 localhost\n'
  for f in "$STATE"/custom*.txt; do
    [ -e "$f" ] || continue
    [ -f "$f" ] && [ ! -L "$f" ] || exit 9
    awk -v mode=custom -f "$PARSE" "$f" || exit 9
  done
} > "$STAGE/next" || { echo 'BH_RESET_ERROR: cannot stage custom mappings' >&2; exit 1; }
[ -s "$STAGE/next" ] || exit 1
if [ "$ACTION" = toggle ]; then
  [ ! -e "$BACKUP" ] || { echo 'BH_RESET_ERROR: backup already exists' >&2; exit 1; }
  cp -p "$TARGET" "$STAGE/previous" || exit 1
  # Move backup into persistent location before touching active hosts.
  mv -f "$STAGE/previous" "$BACKUP" || exit 1
fi
if ! sh "$WRITER" commit "$TARGET" "$STAGE/next"; then
  [ "$ACTION" = toggle ] && rm -f "$BACKUP"
  exit 1
fi
if [ "$ACTION" = reset ]; then
  rm -f "$STATE/bindhosts_state"
  # Reset is explicit, so a previous toggle backup must not later restore blocks.
  rm -f "$BACKUP"
  echo 'BH_RESET_SAFE_PASS'
else
  echo 'BH_RESET_TOGGLED_PASS'
fi
