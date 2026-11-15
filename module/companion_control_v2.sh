#!/system/bin/sh
# BH-APP01 P05 — fixed-verb root interface for verified hosts controls and UX09.
# Do not take user-provided paths, commands, packages, domains or URLs.
set -eu
umask 077
refuse() { printf 'BH_APP01_P05_REFUSED: %s\n' "$1" >&2; exit 2; }
[ "$#" -eq 1 ] || refuse 'one verb required'
ACTION=$1
case "$ACTION" in pause|resume|update-start|update-status|update-events) : ;; *) refuse 'unknown action' ;; esac
if [ "${BH_APP01_V2_TEST_MODE:-0}" = 1 ]; then
    [ "$(id -u)" -ne 0 ] || refuse 'test mode never permitted as root'
    MODDIR=${BH_APP01_V2_TEST_MODDIR:-}
    STATE=${BH_APP01_V2_TEST_STATE:-}
    [ -n "$MODDIR" ] && [ -n "$STATE" ] || refuse 'missing test fixture'
else
    [ -z "${BH_APP01_V2_TEST_MODDIR:-}" ] && [ -z "${BH_APP01_V2_TEST_STATE:-}" ] || refuse 'production path override refused'
    [ "$(id -u)" = 0 ] || refuse 'root required'
    MODDIR=/data/adb/modules/bindhosts
    STATE=/data/adb/bindhosts
fi
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] && [ -d "$STATE" ] && [ ! -L "$STATE" ] || refuse 'module or state unavailable'
[ -f "$MODDIR/bindhosts.sh" ] && [ ! -L "$MODDIR/bindhosts.sh" ] || refuse 'hosts backend unavailable'
[ -f "$MODDIR/hosts_operation_ux09.sh" ] && [ ! -L "$MODDIR/hosts_operation_ux09.sh" ] || refuse 'journaled update backend unavailable'

hosts_state() {
    raw=$(sh "$MODDIR/bindhosts.sh" --hosts-control status 2>/dev/null) || refuse 'hosts status not verified'
    case "$raw" in
      BH_HOSTS_STATE=ACTIVE) HOSTS=ACTIVE ;;
      BH_HOSTS_STATE=PAUSED) HOSTS=PAUSED ;;
      BH_HOSTS_STATE=INACTIVE) HOSTS=INACTIVE ;;
      BH_HOSTS_STATE=DISABLED) HOSTS=DISABLED ;;
      *) refuse 'hosts state invalid' ;;
    esac
}
operation_state() {
    lines=$(sh "$MODDIR/hosts_operation_ux09.sh" status 2>/dev/null) || refuse 'update status not verified'
    state_line=$(printf '%s\n' "$lines" | sed -n '1p')
    case "$state_line" in
      BH_UX09_STATE=IDLE) OP=IDLE ;;
      BH_UX09_STATE=RUNNING) OP=RUNNING ;;
      BH_UX09_STATE=DONE) OP=DONE ;;
      BH_UX09_STATE=FAILED) OP=FAILED ;;
      BH_UX09_STATE=INTERRUPTED) OP=INTERRUPTED ;;
      *) refuse 'update state invalid' ;;
    esac
    STEP=NONE; RECEIPT=NONE
    for line in $(printf '%s\n' "$lines" | sed -n '/^BH_UX09_STEP=/p; /^BH_UX09_RECEIPT=/p'); do
      case "$line" in
        BH_UX09_STEP=PREPARING|BH_UX09_STEP=DOWNLOADING|BH_UX09_STEP=PARSED|BH_UX09_STEP=SKIPPED_DUPLICATE_URL|BH_UX09_STEP=DEDUPLICATING|BH_UX09_STEP=ALLOWLIST|BH_UX09_STEP=GENERATING|BH_UX09_STEP=COMMITTING|BH_UX09_STEP=DONE|BH_UX09_STEP=UNCHANGED|BH_UX09_STEP=FAILED|BH_UX09_STEP=STATS)
            STEP=${line#BH_UX09_STEP=} ;;
        BH_UX09_RECEIPT=PASS|BH_UX09_RECEIPT=FAIL) RECEIPT=${line#BH_UX09_RECEIPT=} ;;
        *) refuse 'unexpected operation metadata' ;;
      esac
    done
}
case "$ACTION" in
  pause|resume)
    hosts_state
    operation_state
    [ "$OP" != RUNNING ] && [ "$OP" != INTERRUPTED ] || refuse 'update running or interrupted'
    if [ "$ACTION" = pause ]; then
      [ "$HOSTS" = ACTIVE ] || refuse 'blocking state changed; active required'
      EXPECT=PAUSED; MARKER=BH_HOSTS_PAUSE_PASS
    else
      [ "$HOSTS" = PAUSED ] || refuse 'blocking state changed; paused required'
      EXPECT=ACTIVE; MARKER=BH_HOSTS_RESUME_PASS
    fi
    # Existing UX08 writer takes the same .hosts-update.lock used by updater.
    output=$(sh "$MODDIR/bindhosts.sh" --hosts-control "$ACTION" 2>/dev/null) || refuse 'safe hosts transition failed'
    printf '%s\n' "$output" | grep -Fqx "$MARKER" || refuse 'verified transition receipt missing'
    hosts_state
    [ "$HOSTS" = "$EXPECT" ] || refuse 'hosts read-back mismatch'
    printf '{"api":2,"action":"%s","hosts":"%s","verified":true}\n' "$ACTION" "$HOSTS"
    ;;
  update-start)
    hosts_state; operation_state
    case "$HOSTS" in ACTIVE|INACTIVE) : ;; *) refuse 'hosts must be active or inactive' ;; esac
    case "$OP" in IDLE|DONE|FAILED) : ;; *) refuse 'unsafe or concurrent update state' ;; esac
    started=$(sh "$MODDIR/hosts_operation_ux09.sh" start 2>/dev/null) || refuse 'safe update launch refused'
    case "$started" in BH_UX09_STARTED=*) : ;; *) refuse 'missing launch receipt' ;; esac
    worker_pid=${started#BH_UX09_STARTED=}
    case "$worker_pid" in ''|*[!0-9]*) refuse 'unsafe launch receipt' ;; esac
    operation_state
    case "$OP:$RECEIPT" in RUNNING:*|DONE:PASS) : ;; *) refuse 'update not confirmed running or done' ;; esac
    printf '{"api":2,"action":"update-start","operation":"%s","accepted":true}\n' "$OP"
    ;;
  update-status)
    operation_state
    printf '{"api":2,"action":"update-status","operation":"%s","step":"%s","receipt":"%s"}\n' "$OP" "$STEP" "$RECEIPT"
    ;;
  update-events)
    # Journaled UX09 returns only sanitized, bounded events, never raw update logs.
    raw_events=$(sh "$MODDIR/hosts_operation_ux09.sh" events 2>/dev/null) || refuse 'operation events unavailable'
    events=$(printf '%s\n' "$raw_events" | tail -n 24) || refuse 'event truncation failed'
    [ "$(printf '%s' "$events" | wc -c)" -le 4600 ] || refuse 'events oversized'
    encoded=$(printf '%s' "$events" | base64 | tr -d '\r\n') || refuse 'event encoding failed'
    case "$encoded" in *[!A-Za-z0-9+/=]*) refuse 'events encoding malformed' ;; esac
    printf '{"api":2,"action":"update-events","encoded":"%s"}\n' "$encoded"
    ;;
esac
