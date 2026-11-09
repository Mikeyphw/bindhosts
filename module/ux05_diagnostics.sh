#!/system/bin/sh
# UX05: bounded, redacted, root-only activity receipts and voluntary diagnostics export.
# Only fixed code identifiers are persisted. No URLs, domains, packages or hosts bytes.
set -eu
umask 077
STATE=${BH_DIAG_STATE:-/data/adb/bindhosts}
MODDIR=${BH_DIAG_MODDIR:-/data/adb/modules/bindhosts}
DIR="$STATE/diagnostics"
EVENTS="$DIR/receipts.psv"
LOCK="$DIR/.receipt-lock"
CMD=${1:-}
[ "$#" -eq 0 ] || shift
err() { printf 'BH_UX05_ERROR: %s\n' "$*" >&2; exit 1; }
[ "${BH_DIAG_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || err 'root required'
[ -d "$STATE" ] && [ ! -L "$STATE" ] || err 'unsafe persistent state'
[ ! -L "$DIR" ] && [ ! -L "$EVENTS" ] && [ ! -L "$LOCK" ] || err 'symlinked diagnostics refused'
[ ! -e "$DIR" ] || [ -d "$DIR" ] || err 'diagnostics directory is not a directory'
[ ! -e "$EVENTS" ] || [ -f "$EVENTS" ] || err 'receipts is not a file'

prepare() {
  [ ! -L "$DIR" ] || err 'symlinked diagnostics directory'
  mkdir -p "$DIR" || err 'cannot create diagnostics directory'
  chmod 0700 "$DIR" || err 'cannot secure diagnostics directory'
  [ ! -e "$EVENTS" ] || [ -f "$EVENTS" ] || err 'invalid receipt file'
  [ ! -L "$EVENTS" ] || err 'symlinked receipt file'
}
valid_record() {
  [ "$#" -eq 4 ] || err 'record AREA ACTION RESULT CODE'
  case "$1" in hosts|recovery|tracker|response|system|config) : ;; *) err 'unknown receipt area' ;; esac
  case "$2" in
    update|reset|toggle|allowlist|commit|recover|monitor|enroll|unenroll|exclude|include|reconcile|block|add|remove|restore|apply|set|start|stop|install|boot|export|probe|create|import) : ;;
    *) err 'unknown receipt operation' ;;
  esac
  case "$3" in ok|fail|warning|info) : ;; *) err 'unknown receipt outcome' ;; esac
  case "$4" in ''|*[!A-Z0-9_]*) err 'receipt codes must be uppercase identifiers' ;; esac
  [ "${#4}" -le 48 ] || err 'receipt code too long'
  # Fixed vocabulary: no arbitrary text can be smuggled into shared exports.
  case "$4" in
    HOSTS_UPDATE_FAILED|HOSTS_UPDATE_OK|HOSTS_RESET_FAILED|HOSTS_RESET_OK|    HOSTS_TOGGLE_FAILED|HOSTS_TOGGLE_OK|HOSTS_ALLOWLIST_FAILED|HOSTS_ALLOWLIST_OK|    HOSTS_ATOMIC_COMMIT|HOSTS_INPLACE_COMMIT|RECOVERY_APPLIED|    RECOVERY_WRITE_FAILED|RECOVERY_ALREADY_DONE|RESPONSE_SET_OK|    RESPONSE_SET_FAILED|RESPONSE_START_FAILED|TG_ACTION_OK|TG_ACTION_FAILED|CONFIG_BACKUP_OK) : ;;
    *) err 'unrecognized receipt code' ;;
  esac
}
record() {
  valid_record "$@"
  prepare
  mkdir "$LOCK" 2>/dev/null || err 'another receipt writer is running'
  trap 'rmdir "$LOCK" 2>/dev/null || :' EXIT
  ts=$(date +%s)
  case "$ts" in ''|*[!0-9]*) err 'invalid device clock' ;; esac
  printf '%s|%s|%s|%s|%s\n' "$ts" "$1" "$2" "$3" "$4" >> "$EVENTS" || err 'could not append receipt'
  chmod 0600 "$EVENTS" || err 'cannot protect receipt file'
  # Keep a fixed upper bound: 400 newest events. Same-dir rename is atomic.
  lines=$(wc -l < "$EVENTS")
  case "$lines" in ''|*[!0-9]*) err 'invalid receipt length' ;; esac
  if [ "$lines" -gt 400 ]; then
    tmp=$(mktemp "$DIR/.receipts-next.XXXXXXXX") || err 'cannot allocate receipt rotation'
    if ! tail -n 400 "$EVENTS" > "$tmp"; then rm -f "$tmp"; err 'receipt rotation failed'; fi
    chmod 0600 "$tmp" || { rm -f "$tmp"; err 'cannot secure receipt rotation'; }
    if ! mv -f "$tmp" "$EVENTS"; then rm -f "$tmp"; err 'could not commit receipt rotation'; fi
  fi
  printf 'BH_UX05_RECORDED\n'
}
limit_value() {
  n=${1:-80}
  case "$n" in ''|*[!0-9]*) err 'history limit must be numeric' ;; esac
  [ "$n" -ge 1 ] && [ "$n" -le 100 ] || err 'history limit must be 1..100'
  LIMIT=$n
}
history() {
  [ "$#" -le 1 ] || err 'history [1..100]'
  limit_value "${1:-80}"
  if [ ! -s "$EVENTS" ]; then printf '[]\n'; return; fi
  # JSON strings contain only allowlisted ASCII identifiers; corrupt records are skipped.
  tail -n "$LIMIT" "$EVENTS" | awk -F'|' '
    BEGIN {first=1;printf "["}
    NF==5 && $1 ~ /^[0-9]+$/ && $2 ~ /^[a-z]+$/ && $3 ~ /^[a-z]+$/ &&
      $4 ~ /^(ok|fail|warning|info)$/ && $5 ~ /^[A-Z0-9_]+$/ {
      if (!first) printf ","; first=0
      printf "{\"ts\":%s,\"area\":\"%s\",\"action\":\"%s\",\"result\":\"%s\",\"code\":\"%s\"}",$1,$2,$3,$4,$5
    }
    END {print "]"}
  '
}
status() {
  [ "$#" -eq 0 ] || err 'status takes no arguments'
  [ ! -e "$STATE/.hosts-target-journal" ] || journal=pending
  journal=${journal:-clean}
  case "$journal" in clean|pending) : ;; *) journal=pending ;; esac
  mode=off
  if [ -f "$STATE/response.mode" ] && [ ! -L "$STATE/response.mode" ]; then mode=$(cat "$STATE/response.mode"); fi
  case "$mode" in off|transparent|logo) : ;; *) mode=unknown ;; esac
  monitor=false
  [ ! -f "$STATE/trackerguard/monitor.enabled" ] || monitor=true
  enabled=0
  if [ -f "$STATE/sources.txt" ] && [ ! -L "$STATE/sources.txt" ]; then
    enabled=$(awk '{line=$0;sub(/^[[:space:]]*/,"",line);if(line!="" && line !~ /^#/ && line !~ /^disabled\|/)n++} END {print n+0}' "$STATE/sources.txt")
  fi
  if [ -s "$EVENTS" ]; then
    metrics=$(awk -F'|' '
      NF==5 && $1 ~ /^[0-9]+$/ && $4 ~ /^(ok|fail|warning|info)$/ && $5 ~ /^[A-Z0-9_]+$/ {
        total++; if ($4=="fail") fails++;
        if ($4=="ok") lastok=$1;
        if ($4=="fail") lastcode=$5;
      }
      END {printf "%d %d %d %s", total+0,fails+0,lastok+0,(lastcode==""?"NONE":lastcode)}
    ' "$EVENTS")
  else metrics='0 0 0 NONE'; fi
  set -- $metrics
  printf '{"schema":1,"receipts":%s,"failures":%s,"last_ok_ts":%s,"last_failure_code":"%s","journal":"%s","response_mode":"%s","monitor_enabled":%s,"enabled_sources":%s}\n' \
    "$1" "$2" "$3" "$4" "$journal" "$mode" "$monitor" "$enabled"
}
export_report() {
  [ "$#" -eq 0 ] || err 'export takes no arguments'
  # Opt-in only. Do not include hostnames, source URLs, package names, app lists,
  # logcat, IFW components or raw system logs in a shareable diagnostic.
  if [ "${BH_DIAG_TEST_MODE:-0}" = 1 ]; then
    OUTDIR=${BH_DIAG_EXPORT_DIR:-"$STATE/downloads"}
  else
    OUTDIR=/storage/emulated/0/Download
  fi
  [ -d "$OUTDIR" ] && [ ! -L "$OUTDIR" ] || err 'Downloads is unavailable or unsafe'
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  case "$stamp" in *[!A-Za-z0-9TZ]*) err 'invalid export timestamp' ;; esac
  dest="$OUTDIR/bindhosts_diagnostics_${stamp}_$$.json"
  [ ! -e "$dest" ] || err 'export target unexpectedly exists'
  tmp=$(mktemp "$OUTDIR/.bindhosts-diagnostics.XXXXXXXX") || err 'cannot create safe export'
  trap 'rm -f "$tmp"' EXIT
  version=unknown
  if [ -f "$MODDIR/module.prop" ]; then
    version=$(sed -n 's/^version=//p' "$MODDIR/module.prop" | head -n 1)
  fi
  case "$version" in ''|*[!A-Za-z0-9_.-]*) version=unknown ;; esac
  {
    printf '{"schema":1,"redacted":true,"version":"%s","summary":' "$version"
    status
    printf ',"receipts":'
    history 100
    printf '}\n'
  } > "$tmp" || err 'failed to write export'
  chmod 0600 "$tmp" || err 'cannot protect export'
  mv -n "$tmp" "$dest" || err 'failed to finalize export'
  trap - EXIT
  printf 'BH_UX05_EXPORT_PATH=%s\n' "$dest"
}
case "$CMD" in
  record) record "$@" ;;
  status) status "$@" ;;
  history) history "$@" ;;
  export) export_report "$@" ;;
  *) err 'usage: record|status|history [limit]|export' ;;
esac
