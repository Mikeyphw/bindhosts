#!/system/bin/sh
# UX04 HTTP + UX07 optional HTTPS blocked-image responder. Default OFF.
set -eu
umask 077
[ "$#" -ge 3 ] || { echo 'BH_RESPONSE_ERROR: usage STATE TARGET status|start|set [off|transparent|logo]' >&2; exit 2; }
STATE=$1; TARGET=$2; CMD=$3; [ "$#" -le 3 ] || shift 3
# UX04 test harness runs without privileged Android context.
[ "${BH_RESPONSE_TEST_MODE:-0}" != 1 ] || export BH_HTTPS_TEST_MODE=1
MODDIR=${BH_RESPONSE_MODDIR:-/data/adb/modules/bindhosts}
MODE_FILE="$STATE/response.mode"; PIDFILE="$STATE/response.pid"
WRITER="$MODDIR/hosts_target_safe.sh"
PORT=${BH_RESPONSE_PORT:-80}
[ "${BH_RESPONSE_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || { echo 'BH_RESPONSE_ERROR: root required' >&2; exit 1; }
[ -d "$STATE" ] && [ ! -L "$STATE" ] && [ -f "$TARGET" ] && [ ! -L "$TARGET" ] || { echo 'BH_RESPONSE_ERROR: unsafe state or target' >&2; exit 1; }
[ ! -L "$MODE_FILE" ] && [ ! -L "$PIDFILE" ] || { echo 'BH_RESPONSE_ERROR: symlink rejected' >&2; exit 1; }
case "$PORT" in ''|*[!0-9]*) exit 2 ;; esac
if [ -n "${BH_RESPONSE_BINARY:-}" ]; then BIN=$BH_RESPONSE_BINARY
else
  ABI=$(getprop ro.product.cpu.abi)
  BIN="$MODDIR/bin/$ABI/blocked_response"
fi
MODE=off
if [ -f "$MODE_FILE" ]; then MODE=$(cat "$MODE_FILE"); fi
case "$MODE" in off|logo|transparent) : ;; *) echo 'BH_RESPONSE_ERROR: bad saved mode' >&2; exit 1 ;; esac
probe() { [ -x "$BIN" ] && "$BIN" --probe --port "$PORT" --mode "$1" >/dev/null 2>&1; }
validpid() {
  [ -s "$PIDFILE" ] || return 1
  _pid=$(cat "$PIDFILE")
  case "$_pid" in ''|*[!0-9]*) return 1 ;; esac
  [ -r "/proc/$_pid/cmdline" ] || return 1
  tr '\000' ' ' < "/proc/$_pid/cmdline" | grep -Fq 'blocked_response' || return 1
  kill -0 "$_pid" 2>/dev/null
}
stop_server() {
  if validpid; then
    _pid=$(cat "$PIDFILE")
    kill "$_pid" 2>/dev/null || :
    _n=0
    # A reaped or zombie child is stopped; do not wait ten seconds on a zombie
    # that still answers kill -0 while its parent has not called wait(2).
    while kill -0 "$_pid" 2>/dev/null && [ "$_n" -lt 20 ]; do
      if [ -r "/proc/$_pid/status" ] &&
         grep -Eq '^State:[[:space:]]*Z' "/proc/$_pid/status"; then break; fi
      sleep 0.1
      _n=$((_n+1))
    done
  fi
  rm -f "$PIDFILE"
}
start_server() {
  _wanted=$1
  [ -x "$BIN" ] || { echo 'BH_RESPONSE_ERROR: CI-built responder unavailable for this ABI' >&2; return 1; }
  probe "$_wanted" && return 0
  # Never terminate an unknown process listening on port 80.
  if validpid; then stop_server; else
    if "$BIN" --probe --port "$PORT" --mode logo >/dev/null 2>&1 ||
       "$BIN" --probe --port "$PORT" --mode transparent >/dev/null 2>&1; then
      echo 'BH_RESPONSE_ERROR: another bindhosts responder owns port; refusing unknown PID' >&2
      return 1
    fi
  fi
  "$BIN" --port "$PORT" --mode "$_wanted" >/dev/null 2>&1 &
  _pid=$!; printf '%s\n' "$_pid" > "$PIDFILE"
  _i=0
  while [ "$_i" -lt 8 ]; do
    probe "$_wanted" && { echo 'BH_RESPONSE_SERVER_READY'; return 0; }
    kill -0 "$_pid" 2>/dev/null || break
    sleep 1; _i=$((_i+1))
  done
  stop_server
  echo 'BH_RESPONSE_ERROR: cannot bind loopback HTTP port' >&2
  return 1
}
save_mode() {
  _m=$1
  _tmp=$(mktemp "$STATE/.response-mode.XXXXXXXX") || return 1
  printf '%s\n' "$_m" > "$_tmp"
  chmod 0600 "$_tmp"
  mv -f "$_tmp" "$MODE_FILE"
}
switch_hosts() {
  _mode=$1
  [ -f "$WRITER" ] || { echo 'BH_RESPONSE_ERROR: hosts target writer missing' >&2; return 1; }
  # Marked sections are required so explicitly mapped custom hosts stay unchanged.
  if [ "$(grep -Fxc '# bindhosts-block-start' "$TARGET")" != 1 ] ||
     [ "$(grep -Fxc '# bindhosts-block-end' "$TARGET")" != 1 ]; then
    # Reset intentionally removes all managed block sections. Turning the
    # responder OFF must remain possible without rebuilding those sections.
    if [ "$_mode" = off ] && ! grep -Fq '# bh-response' "$TARGET"; then
      echo 'BH_RESPONSE_NO_MANAGED_BLOCKS: already using standard hosts'; return 0
    fi
    echo 'BH_RESPONSE_ERROR: run a normal hosts Update first to establish managed sections' >&2
    return 1
  fi
  _tmp=$(mktemp "$STATE/.response-convert.XXXXXXXX") || return 1
  if ! awk -v m="$_mode" '
    /^# bindhosts-block-start$/ {inside=1;print;next}
    /^# bindhosts-block-end$/ {inside=0;print;next}
    inside && m!="off" && $1=="0.0.0.0" && NF==2 {print "127.0.0.1",$2,"# bh-response";next}
    inside && m=="off" && $1=="127.0.0.1" && $3=="#" && $4=="bh-response" {print "0.0.0.0",$2;next}
    {print}
  ' "$TARGET" > "$_tmp"; then rm -f "$_tmp"; return 1; fi
  BH_HOSTS_ROOT="$STATE" sh "$WRITER" commit "$TARGET" "$_tmp"
  _rc=$?; rm -f "$_tmp"; return "$_rc"
}
case "$CMD" in
  stop)
    if [ -f "$MODDIR/https_response.sh" ]; then
      sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" stop || :
    fi
    stop_server; echo BH_RESPONSE_STOPPED ;;
  status)
    echo "mode=$MODE"
    if [ "$MODE" != off ] && probe "$MODE"; then echo 'server=running'; else echo 'server=not_running'; fi
    if [ -f "$MODDIR/https_response.sh" ]; then
      sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" status
    else
      echo 'https_mode=unsupported'
    fi
    echo 'https_replacement=conditional_user_ca_trust_required'

    ;;
  start)
    if [ "$MODE" != off ]; then
      # A failed boot start must not leave persistent block mappings routed to
      # an unrelated future process on localhost port 80. Fail closed to 0.0.0.0.
      if ! start_server "$MODE"; then
        echo 'BH_RESPONSE_BOOT_START_FAILED: reverting managed hosts mappings' >&2
        if switch_hosts off && save_mode off; then
          echo 'BH_RESPONSE_FAIL_CLOSED_PASS: responder disabled after start failure' >&2
        else
          echo 'BH_RESPONSE_RECOVERY_REQUIRED: cannot restore standard mappings' >&2
        fi
        if [ -f "$MODDIR/https_response.sh" ]; then
          sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" disable >/dev/null 2>&1 || :
        fi
        exit 1
      fi
    fi
    if [ -f "$MODDIR/https_response.sh" ]; then
      sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" start ||
        echo 'BH_RESPONSE_HTTPS_BOOT_FAILED_DISABLED: HTTP remains active' >&2
    fi
    ;;
  https)
    [ -f "$MODDIR/https_response.sh" ] || { echo 'BH_RESPONSE_ERROR: UX07 backend missing' >&2; exit 1; }
    [ "$#" -eq 1 ] || { echo 'BH_RESPONSE_ERROR: https requires one action' >&2; exit 2; }
    sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" "$1" ;;
  set)
    [ "$#" -eq 1 ] || { echo 'BH_RESPONSE_ERROR: set requires mode' >&2; exit 2; }
    WANTED=$1
    case "$WANTED" in off|transparent|logo) : ;; *) echo 'BH_RESPONSE_ERROR: unsupported mode' >&2; exit 2 ;; esac
    if [ "$WANTED" = "$MODE" ]; then
      # User may reapply the selected mode after a server crash; never claim
      # success while localhost is not serving the selected image.
      if [ "$MODE" != off ] && ! probe "$MODE"; then
        start_server "$MODE" || exit 1
        echo 'BH_RESPONSE_SERVER_REPAIRED'
      fi
      if [ "$MODE" = off ]; then stop_server; fi
      if [ -f "$MODDIR/https_response.sh" ]; then
        sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" sync ||
          echo 'BH_RESPONSE_HTTPS_SYNC_FAILED_DISABLED' >&2
      fi
      echo 'BH_RESPONSE_MODE_UNCHANGED'

      exit 0
    fi
    if [ "$WANTED" = off ]; then
      switch_hosts off || exit 1
      if ! save_mode off; then
        # The saved configuration still requests the previous mode; restore its
        # block mappings rather than silently diverging from persistent state.
        switch_hosts "$MODE" || echo 'BH_RESPONSE_RECOVERY_REQUIRED: mode save failed and mappings could not be restored' >&2
        echo 'BH_RESPONSE_ERROR: failed to persist disabled mode' >&2
        exit 1
      fi
      stop_server
      if [ -f "$MODDIR/https_response.sh" ]; then
        sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" disable || :
      fi
    else
      start_server "$WANTED" || exit 1
      # Save mode before mapping hosts; a crash leaves a boot-restartable server.
      if ! save_mode "$WANTED"; then
        if [ "$MODE" = off ]; then stop_server; else start_server "$MODE" || :; fi
        echo 'BH_RESPONSE_ERROR: failed to persist requested mode' >&2
        exit 1
      fi
      if ! switch_hosts "$WANTED"; then
        save_mode "$MODE"
        if [ "$MODE" = off ]; then stop_server; else start_server "$MODE" || :; fi
        echo 'BH_RESPONSE_ERROR: hosts unchanged; response mode rolled back' >&2
        exit 1
      fi
    fi
    if [ -f "$MODDIR/https_response.sh" ]; then
      sh "$MODDIR/https_response.sh" "$STATE" "$TARGET" sync ||
        echo 'BH_RESPONSE_HTTPS_SYNC_FAILED_DISABLED: HTTP still active' >&2
    fi
    echo "BH_RESPONSE_MODE_PASS: $WANTED"
    ;;
  *) echo 'BH_RESPONSE_ERROR: unknown command' >&2; exit 2 ;;
esac
