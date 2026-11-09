#!/system/bin/sh
# UX07: explicitly enabled, loopback-only HTTPS blocked-image server.
# Never installs a CA, changes system trust, forwards traffic or alters hosts.
set -eu
umask 077
[ "$#" -ge 3 ] || { echo 'BH_HTTPS_ERROR: usage STATE TARGET status|cert-create|cert-export|enable|disable|start|stop|test' >&2; exit 2; }
STATE=$1; TARGET=$2; CMD=$3; shift 3
[ "$#" -eq 0 ] || { echo 'BH_HTTPS_ERROR: unexpected arguments' >&2; exit 2; }
MODDIR=${BH_HTTPS_MODDIR:-/data/adb/modules/bindhosts}
TLS_DIR="$STATE/.ux07-tls"
CERT="$TLS_DIR/ca.crt"; KEY="$TLS_DIR/ca.key"
FLAG="$STATE/https.enabled"; PIDFILE="$STATE/https.pid"
PORT=${BH_HTTPS_PORT:-443}
DOWNLOAD=${BH_HTTPS_DOWNLOAD:-/storage/emulated/0/Download}
if [ "${BH_HTTPS_TEST_MODE:-0}" != 1 ]; then
  [ "$(id -u)" = 0 ] || { echo 'BH_HTTPS_ERROR: root required' >&2; exit 1; }
  PORT=443
fi
[ -d "$STATE" ] && [ ! -L "$STATE" ] && [ -f "$TARGET" ] && [ ! -L "$TARGET" ] || { echo 'BH_HTTPS_ERROR: unsafe hosts/state path' >&2; exit 1; }
[ ! -L "$FLAG" ] && [ ! -L "$PIDFILE" ] && [ ! -L "$TLS_DIR" ] && [ ! -L "$CERT" ] && [ ! -L "$KEY" ] || { echo 'BH_HTTPS_ERROR: symbolic link rejected' >&2; exit 1; }
case "$PORT" in ''|*[!0-9]*) exit 2 ;; esac
if [ -n "${BH_HTTPS_BINARY:-}" ]; then BIN=$BH_HTTPS_BINARY
else
  if command -v getprop >/dev/null 2>&1; then ABI=$(getprop ro.product.cpu.abi)
  else ABI=unavailable; fi
  BIN="$MODDIR/bin/$ABI/blocked_response_tls"
fi
MODE=off
if [ -f "$STATE/response.mode" ]; then MODE=$(cat "$STATE/response.mode"); fi
case "$MODE" in off|logo|transparent) : ;; *) echo 'BH_HTTPS_ERROR: invalid HTTP mode' >&2; exit 1 ;; esac

validpid() {
  [ -s "$PIDFILE" ] || return 1
  _pid=$(cat "$PIDFILE")
  case "$_pid" in ''|*[!0-9]*) return 1 ;; esac
  [ -r "/proc/$_pid/cmdline" ] || return 1
  tr '\000' ' ' < "/proc/$_pid/cmdline" | grep -Fq 'blocked_response_tls' || return 1
  kill -0 "$_pid" 2>/dev/null
}
stop_server() {
  if validpid; then
    _pid=$(cat "$PIDFILE")
    kill "$_pid" 2>/dev/null || :
    _i=0
    while kill -0 "$_pid" 2>/dev/null && [ "$_i" -lt 20 ]; do
      if [ -r "/proc/$_pid/status" ] && grep -Eq '^State:[[:space:]]*Z' "/proc/$_pid/status"; then break; fi
      sleep 0.1; _i=$((_i+1))
    done
  fi
  rm -f "$PIDFILE"
}
probe() { [ -x "$BIN" ] && "$BIN" --action probe --state "$TLS_DIR" --port "$PORT" --mode "$MODE" >/dev/null 2>&1; }
start_server() {
  [ "$MODE" != off ] || { echo 'BH_HTTPS_ERROR: enable HTTP image response first' >&2; return 1; }
  [ -x "$BIN" ] || { echo 'BH_HTTPS_ERROR: CI-built TLS responder missing for current ABI' >&2; return 1; }
  [ -f "$CERT" ] && [ -f "$KEY" ] || { echo 'BH_HTTPS_ERROR: generate private certificate first' >&2; return 1; }
  if probe; then
    validpid || { echo 'BH_HTTPS_ERROR: responder answered but owner PID unknown' >&2; return 1; }
    return 0
  fi
  # Never kill an unrelated process on port 443.
  if validpid; then stop_server; fi
  "$BIN" --action serve --state "$TLS_DIR" --hosts "$TARGET" --mode "$MODE" --port "$PORT" >/dev/null 2>&1 &
  _pid=$!; printf '%s\n' "$_pid" > "$PIDFILE"
  _i=0
  while [ "$_i" -lt 8 ]; do
    if probe; then echo 'BH_HTTPS_SERVER_READY'; return 0; fi
    kill -0 "$_pid" 2>/dev/null || break
    sleep 1; _i=$((_i+1))
  done
  stop_server
  echo 'BH_HTTPS_ERROR: cannot start localhost TLS service (port/SELinux/certificate)' >&2
  return 1
}
cert_status() {
  if [ -f "$CERT" ] || [ -f "$KEY" ]; then
    if [ -f "$CERT" ] && [ -f "$KEY" ] && [ -x "$BIN" ]; then
      _details=$("$BIN" --action cert-status --state "$TLS_DIR" 2>/dev/null) || _details=''
      if printf '%s\n' "$_details" | grep -Eq '^fingerprint_sha256=[0-9A-F]{64}$'; then
        echo 'certificate=present'
        printf 'certificate_%s\n' "$_details"
        return
      fi
    fi
    echo 'certificate=invalid'
  else echo 'certificate=absent'; fi
}
case "$CMD" in
  status)
    if [ -f "$FLAG" ]; then echo 'https_mode=enabled'; else echo 'https_mode=off'; fi
    if [ "$MODE" != off ] && probe && validpid; then echo 'https_server=running'; else echo 'https_server=not_running'; fi
    cert_status
    echo 'android_trust=not_verified'
    ;;
  cert-create)
    [ -x "$BIN" ] || { echo 'BH_HTTPS_ERROR: TLS binary missing' >&2; exit 1; }
    "$BIN" --action cert-create --state "$TLS_DIR"
    "$BIN" --action cert-status --state "$TLS_DIR"
    echo 'BH_HTTPS_CERT_INSTALL_IS_MANUAL'
    ;;
  cert-status)
    cert_status
    ;;
  cert-export)
    [ -f "$CERT" ] && [ ! -L "$CERT" ] && [ -x "$BIN" ] || { echo 'BH_HTTPS_ERROR: valid CA required' >&2; exit 1; }
    _fp=$("$BIN" --action cert-status --state "$TLS_DIR" | sed -n 's/^fingerprint_sha256=//p') || exit 1
    [ "${#_fp}" -eq 64 ] || { echo 'BH_HTTPS_ERROR: invalid fingerprint length' >&2; exit 1; }
    case "$_fp" in *[!0-9A-F]*) echo 'BH_HTTPS_ERROR: bad fingerprint' >&2; exit 1 ;; esac
    [ -d "$DOWNLOAD" ] && [ ! -L "$DOWNLOAD" ] || { echo 'BH_HTTPS_ERROR: Downloads unavailable' >&2; exit 1; }
    _dest="$DOWNLOAD/bindhosts-local-ca-${_fp%????????????????????????????????????????????????}.crt"
    # The native export verifies the exact fingerprint-derived basename and
    # uses O_CREAT|O_EXCL plus fsync. No overwrite or symlink follow is possible.
    "$BIN" --action cert-export --state "$TLS_DIR" --dest "$_dest" || exit 1
    echo "BH_HTTPS_CERT_EXPORTED: $_dest"
    echo 'BH_HTTPS_CA_INSTALL_REQUIRES_ANDROID_USER_ACTION'
    ;;
  enable)
    [ ! -f "$FLAG" ] || { start_server; echo 'BH_HTTPS_ALREADY_ENABLED'; exit 0; }
    start_server || exit 1
    _tmp=$(mktemp "$STATE/.https-enabled.XXXXXXXX") || { stop_server; exit 1; }
    printf 'enabled\n' > "$_tmp"; chmod 0600 "$_tmp"
    mv -f "$_tmp" "$FLAG" || { rm -f "$_tmp"; stop_server; exit 1; }
    echo 'BH_HTTPS_ENABLED_ANDROID_TRUST_UNVERIFIED'
    ;;
  disable)
    rm -f "$FLAG" || exit 1
    stop_server
    echo 'BH_HTTPS_DISABLED_CA_REMAINS_INSTALLED_IF_USER_ADDED_IT'
    ;;
  stop) stop_server; echo 'BH_HTTPS_STOPPED' ;;
  start)
    if [ -f "$FLAG" ]; then
      if ! start_server; then
        rm -f "$FLAG"
        stop_server
        echo 'BH_HTTPS_START_FAILED_DISABLED' >&2
        exit 1
      fi
    fi
    ;;
  sync)
    if [ -f "$FLAG" ]; then
      if [ "$MODE" = off ]; then rm -f "$FLAG"; stop_server
      elif ! start_server; then rm -f "$FLAG"; stop_server; echo 'BH_HTTPS_SYNC_FAILED_DISABLED' >&2; exit 1
      fi
    fi
    ;;
  test)
    if probe && validpid; then echo 'BH_HTTPS_LOCAL_TLS_PASS_ANDROID_TRUST_UNVERIFIED'
    else echo 'BH_HTTPS_TEST_FAILED: TLS handshake or image response failed' >&2; exit 1; fi
    ;;
  *) echo 'BH_HTTPS_ERROR: unknown command' >&2; exit 2 ;;
esac
