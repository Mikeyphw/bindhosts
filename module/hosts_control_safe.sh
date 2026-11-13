#!/system/bin/sh
# UX08: explicit, read-back-verified hosts controls; no checksum-driven toggles.
# status is read-only. pause/resume use existing journaled hosts writer and rollback.
set -eu
umask 077
[ "$#" -eq 4 ] || { echo 'BH_HOSTS_REFUSED: expected ACTION TARGET STATE MODULE' >&2; exit 2; }
ACTION=$1; TARGET=$2; STATE=$3; MODDIR=$4
case "$ACTION" in status|pause|resume|update) : ;; *) echo 'BH_HOSTS_REFUSED: unknown action' >&2; exit 2 ;; esac
fail() { printf 'BH_HOSTS_REFUSED: %s\n' "$1" >&2; exit 1; }
[ -d "$STATE" ] && [ ! -L "$STATE" ] && [ -f "$TARGET" ] && [ ! -L "$TARGET" ] && [ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] || fail 'invalid state, module, or hosts target'
BACKUP="$STATE/bindhosts_backup"
[ ! -L "$BACKUP" ] || fail 'unsafe pause backup'
[ ! -e "$BACKUP" ] || [ -f "$BACKUP" ] || fail 'invalid pause backup'

read_state() {
  if [ -f "$MODDIR/disable" ]; then printf 'DISABLED\n'; return 0; fi
  if [ -f "$BACKUP" ]; then
    if grep -Fq '# bindhosts-block-start' "$TARGET"; then
      printf 'INCONSISTENT\n'; return 0
    fi
    printf 'PAUSED\n'; return 0
  fi
  if grep -Fq '# bindhosts-block-start' "$TARGET" &&
     grep -Fq '# bindhosts-block-end' "$TARGET" &&
     grep -Fq '# bindhosts v' "$TARGET"; then
    printf 'ACTIVE\n'
  else
    printf 'INACTIVE\n'
  fi
}
STATE_NOW=$(read_state)
if [ "$ACTION" = status ]; then
  printf 'BH_HOSTS_STATE=%s\n' "$STATE_NOW"
  [ "$STATE_NOW" != INCONSISTENT ] || exit 1
  exit 0
fi
[ "${BH_HOSTS_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || fail 'root required'
[ "$STATE_NOW" != DISABLED ] || fail 'module disabled'
[ "$STATE_NOW" != INCONSISTENT ] || fail 'pause backup conflicts with generated hosts'

case "$ACTION" in
  pause|resume)
    [ -f "$MODDIR/hosts_reset_safe.sh" ] && [ -f "$MODDIR/hosts_target_safe.sh" ] || fail 'safe hosts writer unavailable'
    if [ "$ACTION" = pause ]; then
      [ "$STATE_NOW" = ACTIVE ] || fail 'blocking not active; update first'
      EXPECTED=PAUSED
    else
      [ "$STATE_NOW" = PAUSED ] || fail 'blocking is not paused'
      EXPECTED=ACTIVE
    fi
    # The update pipeline uses this same lock. Prevent a scheduled update from
    # racing a manual pause/restore and silently undoing the user's choice.
    LOCK="$STATE/.hosts-update.lock"
    mkdir "$LOCK" 2>/dev/null || fail 'another hosts operation is running'
    trap 'rmdir "$LOCK" 2>/dev/null || :' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    [ "$(read_state)" = "$STATE_NOW" ] || fail 'state changed before action'
    sh "$MODDIR/hosts_reset_safe.sh" toggle "$TARGET" "$STATE" "$MODDIR" || fail 'journaled hosts transition failed'
    [ "$(read_state)" = "$EXPECTED" ] || fail 'hosts read-back did not match requested state'
    # Keep the Home-page module description consistent with the verified state.
    # UI confirmation still depends on hosts read-back, never this metadata.
    if [ -f "$MODDIR/module.prop" ] && [ ! -L "$MODDIR/module.prop" ]; then
      if [ "$ACTION" = pause ]; then
        DESCRIPTION='description=status: paused | hosts blocking suspended'
      else
        DESCRIPTION='description=status: active | hosts blocking restored'
      fi
      sed -i "s/^description=.*/$DESCRIPTION/" "$MODDIR/module.prop" ||
        echo 'BH_HOSTS_WARNING: module description could not be refreshed' >&2
    fi
    if [ "$ACTION" = pause ]; then printf 'BH_HOSTS_PAUSE_PASS\n'; else printf 'BH_HOSTS_RESUME_PASS\n'; fi
    ;;
  update)
    [ "$STATE_NOW" != PAUSED ] || fail 'blocking paused; resume before updating'
    [ -f "$MODDIR/bindhosts.sh" ] || fail 'update backend unavailable'
    sh "$MODDIR/bindhosts.sh" --force-update || fail 'hosts update failed; previous data retained when possible'
    [ "$(read_state)" = ACTIVE ] || fail 'update finished without active hosts read-back'
    printf 'BH_HOSTS_UPDATE_PASS\n'
    ;;
esac
