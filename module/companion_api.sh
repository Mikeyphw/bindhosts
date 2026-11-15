#!/system/bin/sh
# BH-APP01: deliberately read-only, finite root API for the companion foundation.
# No arbitrary command, path, JSON argument, or writable operation is accepted.
set -eu
umask 077
refuse() { printf 'BH_APP01_REFUSED: %s\n' "$1" >&2; exit 2; }
[ "$#" -eq 1 ] || refuse 'expected exactly one operation'
case "$1" in hello|status) : ;; *) refuse 'unknown or write operation' ;; esac

# Fixture injection exists ONLY for non-rooted source tests. Never allow the
# rooted service to redirect itself to an attacker-controlled module directory.
if [ "${BH_APP01_TEST_MODE:-0}" = 1 ]; then
    [ "$(id -u)" -ne 0 ] || refuse 'test mode refused as root'
    MODDIR=${BH_APP01_TEST_MODDIR:-}; STATE=${BH_APP01_TEST_STATE:-}
    [ -n "$MODDIR" ] && [ -n "$STATE" ] || refuse 'incomplete test fixture'
else
    [ -z "${BH_APP01_TEST_MODDIR:-}" ] && [ -z "${BH_APP01_TEST_STATE:-}" ] || refuse 'production path override refused'
    MODDIR=/data/adb/modules/bindhosts
    STATE=/data/adb/bindhosts
fi
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] || refuse 'module unavailable or unsafe'
[ -f "$MODDIR/module.prop" ] && [ ! -L "$MODDIR/module.prop" ] || refuse 'module metadata unavailable'
[ -f "$MODDIR/bindhosts.sh" ] && [ ! -L "$MODDIR/bindhosts.sh" ] || refuse 'module backend unavailable'
[ -d "$STATE" ] && [ ! -L "$STATE" ] || refuse 'state unavailable or unsafe'

# Only a numeric version code is used; no unsanitized property values in JSON.
version=$(sed -n 's/^versionCode=//p' "$MODDIR/module.prop" | head -n 1)
case "$version" in ''|*[!0-9]*) refuse 'invalid module version' ;; esac
[ "${#version}" -le 10 ] || refuse 'invalid module version length'

case "$1" in
  hello)
    printf '{"api":1,"module":"bindhosts","versionCode":%s,"capabilities":["hello","status"]}\n' "$version"
    ;;
  status)
    # Use the same read-back status contract as the UX08 WebUI.
    raw=$(sh "$MODDIR/bindhosts.sh" --hosts-control status 2>/dev/null) || refuse 'hosts status unavailable'
    case "$raw" in
      BH_HOSTS_STATE=ACTIVE) hosts=ACTIVE ;;
      BH_HOSTS_STATE=PAUSED) hosts=PAUSED ;;
      BH_HOSTS_STATE=INACTIVE) hosts=INACTIVE ;;
      BH_HOSTS_STATE=DISABLED) hosts=DISABLED ;;
      *) refuse 'unrecognized hosts state' ;;
    esac
    operation=IDLE
    if [ -f "$MODDIR/hosts_operation_ux09.sh" ] && [ ! -L "$MODDIR/hosts_operation_ux09.sh" ]; then
      operation_output=$(sh "$MODDIR/hosts_operation_ux09.sh" status 2>/dev/null) || refuse 'update status unavailable'
      first_line=$(printf '%s\n' "$operation_output" | sed -n '1p')
      case "$first_line" in
        BH_UX09_STATE=IDLE) operation=IDLE ;;
        BH_UX09_STATE=RUNNING) operation=RUNNING ;;
        BH_UX09_STATE=DONE) operation=DONE ;;
        BH_UX09_STATE=FAILED) operation=FAILED ;;
        BH_UX09_STATE=INTERRUPTED) operation=INTERRUPTED ;;
        *) refuse 'unrecognized update state' ;;
      esac
    fi
    printf '{"api":1,"hosts":"%s","operation":"%s"}\n' "$hosts" "$operation"
    ;;
esac
