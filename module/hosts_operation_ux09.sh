#!/system/bin/sh
# UX09: private, detached hosts-update coordinator. No cancellation or device-wide mutations.
set -eu
umask 077
ROOT=${BH_UX09_ROOT:-/data/adb/bindhosts}
MODDIR=${BH_UX09_MODDIR:-/data/adb/modules/bindhosts}
OP="$ROOT/.ux09-operation"
LOCK="$ROOT/.ux09-launch.lock"
fail() { printf 'BH_UX09_REFUSED: %s\n' "$1" >&2; exit 1; }
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] || fail 'unsafe state directory'
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] || fail 'unsafe module directory'
checkfile() { [ ! -L "$OP/$1" ] || fail 'unsafe private operation file'; }
if [ -e "$OP" ] || [ -L "$OP" ]; then
    [ -d "$OP" ] && [ ! -L "$OP" ] || fail 'unsafe operation directory'
    for f in state events.tsv receipt pid raw.log; do checkfile "$f"; done
fi
case "${1:-}" in
  status)
    if [ ! -f "$OP/state" ]; then echo 'BH_UX09_STATE=IDLE'; exit 0; fi
    state=$(cat "$OP/state")
    case "$state" in RUNNING|DONE|FAILED) : ;; *) fail 'unrecognized operation state' ;; esac
    if [ "$state" = RUNNING ] && [ -f "$OP/pid" ]; then
      pid=$(cat "$OP/pid"); case "$pid" in ''|*[!0-9]*) fail 'invalid worker PID' ;; esac
      if ! kill -0 "$pid" 2>/dev/null; then state=INTERRUPTED; fi
    fi
    printf 'BH_UX09_STATE=%s\n' "$state"
    if [ -f "$OP/events.tsv" ]; then
      last=$(tail -n 1 "$OP/events.tsv" || :)
      case "$last" in
        *'|'*) step=${last%%|*}; case "$step" in PREPARING|DOWNLOADING|PARSED|DEDUPLICATING|ALLOWLIST|GENERATING|COMMITTING|DONE|UNCHANGED|FAILED|STATS|SKIPPED_DUPLICATE_URL) printf 'BH_UX09_STEP=%s\n' "$step" ;; esac ;;
      esac
    fi
    if [ -f "$OP/receipt" ]; then
      receipt=$(cat "$OP/receipt"); case "$receipt" in PASS|FAIL) printf 'BH_UX09_RECEIPT=%s\n' "$receipt" ;; esac
    fi
    ;;
  events)
    [ -f "$OP/events.tsv" ] || exit 0
    tail -n 150 "$OP/events.tsv" | LC_ALL=C awk -F'|' '
       NF>=2 && $1 ~ /^[A-Z_]+$/ && $2 ~ /^[A-Za-z0-9_ .=:-]+$/ && length($0)<180 {print}
    '
    ;;
  start)
    [ "${BH_UX09_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || fail 'root required'
    mkdir "$LOCK" 2>/dev/null || fail 'another update launcher is running'
    trap 'rmdir "$LOCK" 2>/dev/null || :' EXIT
    [ -d "$OP" ] || mkdir -m 700 "$OP" || fail 'cannot create private operation directory'
    [ ! -L "$OP" ] || fail 'unsafe operation directory'
    for f in state events.tsv receipt pid raw.log; do checkfile "$f"; done
    if [ -f "$OP/state" ] && [ "$(cat "$OP/state")" = RUNNING ]; then
      if [ ! -f "$OP/pid" ]; then fail 'operation startup in progress'; fi
      oldpid=$(cat "$OP/pid")
      case "$oldpid" in ''|*[!0-9]*) fail 'unsafe worker PID' ;; esac
      if kill -0 "$oldpid" 2>/dev/null; then fail 'an update is already running'; fi
      fail 'previous operation interrupted; inspect before retrying'
    fi
    : > "$OP/events.tsv"; : > "$OP/raw.log"; rm -f "$OP/receipt"
    printf 'RUNNING\n' > "$OP/state"
    # Noninteractive stdin and closed descriptors prevent a WebUI promise from
    # waiting for the update itself. The result is always checked via status.
    sh "$0" worker </dev/null >/dev/null 2>&1 &
    pid=$!
    printf '%s\n' "$pid" > "$OP/pid"
    printf 'BH_UX09_STARTED=%s\n' "$pid"
    ;;
  worker)
    [ "${BH_UX09_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || fail 'root required'
    [ -d "$OP" ] && [ ! -L "$OP" ] && [ -f "$OP/state" ] || fail 'operation state unavailable'
    if [ "${BH_UX09_TEST_MODE:-0}" = 1 ] && [ -n "${BH_UX09_TEST_COMMAND:-}" ]; then
      sh "$BH_UX09_TEST_COMMAND" > "$OP/raw.log" 2>&1 && ok=1 || ok=0
    else
      BH_UX09_EVENTS="$OP/events.tsv" sh "$MODDIR/bindhosts.sh" --hosts-control update > "$OP/raw.log" 2>&1 && ok=1 || ok=0
    fi
    if [ "$ok" = 1 ] && grep -Fqx 'BH_HOSTS_UPDATE_PASS' "$OP/raw.log"; then
      printf 'PASS\n' > "$OP/receipt"
      printf 'DONE\n' > "$OP/state"
    else
      printf 'FAILED|Backend refused update; existing hosts may have been preserved\n' >> "$OP/events.tsv"
      printf 'FAIL\n' > "$OP/receipt"
      printf 'FAILED\n' > "$OP/state"
    fi
    ;;
  *) fail 'usage: start|status|events' ;;
esac
