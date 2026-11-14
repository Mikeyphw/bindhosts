#!/system/bin/sh
# UX02 fail-closed sources pipeline. Stage + validate before touching active hosts.
# Usage: hosts_update_safe.sh STATE_DIR TARGET_HOSTS WORK_DIR VERSIONCODE
set -eu
umask 077
[ "$#" -eq 4 ] || { echo 'BH_UPDATE_ERROR: usage STATE TARGET WORK VERSION' >&2; exit 2; }
ROOT=$1; TARGET=$2; WORK=$3; VERSION=$4
MODDIR=${BH_UPDATE_MODDIR:-/data/adb/modules/bindhosts}
PARSE="$MODDIR/hosts_update_parse.awk"
[ "${BH_UPDATE_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || { echo 'BH_UPDATE_ERROR: root required' >&2; exit 1; }
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] && [ -f "$TARGET" ] && [ ! -L "$TARGET" ] && [ -f "$PARSE" ] || { echo 'BH_UPDATE_ERROR: unsafe paths' >&2; exit 1; }
case "$VERSION" in ''|*[!0-9]*) echo 'BH_UPDATE_ERROR: invalid version' >&2; exit 1 ;; esac
LOCK="$ROOT/.hosts-update.lock"; STAGE=''; NEXT_TARGET=''; LOCKED=0
fail() { printf 'BH_UPDATE_ERROR: %s; existing hosts preserved until commit\n' "$*" >&2; exit 1; }
cleanup() {
  [ -z "$NEXT_TARGET" ] || rm -f "$NEXT_TARGET"
  [ -z "$STAGE" ] || rm -rf "$STAGE"
  [ "$LOCKED" = 0 ] || rmdir "$LOCK" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$LOCK" 2>/dev/null || fail 'another hosts update is running'
LOCKED=1
# Snapshot the configured source fingerprint BEFORE downloads. Source edits
# during an update remain visibly pending rather than being falsely marked applied.
ux09_source_hash=$(sha256sum "$ROOT/sources.txt" 2>/dev/null | awk '{print $1}') || ux09_source_hash=''
# UX09 progress uses a private, fixed path. No URLs or domains enter the event stream.
ux09_event() {
  [ -n "${BH_UX09_EVENTS:-}" ] || return 0
  [ "$BH_UX09_EVENTS" = "$ROOT/.ux09-operation/events.tsv" ] || return 0
  [ -f "$BH_UX09_EVENTS" ] && [ ! -L "$BH_UX09_EVENTS" ] || return 0
  printf '%s|%s\n' "$1" "$2" >> "$BH_UX09_EVENTS" || :
}
ux09_applied() {
  [ ! -L "$ROOT/.sources-applied.sha256" ] || return 0
  _hash=$ux09_source_hash
  case "$_hash" in *[!a-f0-9]*|'') return 0 ;; esac
  [ "${#_hash}" = 64 ] || return 0
  _tmp=$(mktemp "$ROOT/.ux09-applied.XXXXXXXX") || return 0
  if printf '%s\n' "$_hash" > "$_tmp" && chmod 0600 "$_tmp" && mv -f "$_tmp" "$ROOT/.sources-applied.sha256"; then
    [ ! -L "$ROOT/.sources-applied.epoch" ] || return 0
    _epoch=$(date +%s) || return 0
    case "$_epoch" in ''|*[!0-9]*) return 0 ;; esac
    _stamp=$(mktemp "$ROOT/.ux09-epoch.XXXXXXXX") || return 0
    printf '%s\n' "$_epoch" > "$_stamp" && chmod 0600 "$_stamp" && mv -f "$_stamp" "$ROOT/.sources-applied.epoch" || { rm -f "$_stamp"; :; }
  else
    rm -f "$_tmp"
  fi
}
ux09_event PREPARING 'Private staging and configuration verification'
# Shared with the explicit pause/resume controller. Refuse even cron updates
# while paused; otherwise a scheduled update would silently resume blocking.
[ ! -e "$ROOT/bindhosts_backup" ] && [ ! -L "$ROOT/bindhosts_backup" ] || fail 'blocking paused; resume before updating'
STAGE=$(mktemp -d "$ROOT/.hosts-update.XXXXXXXX") || fail 'cannot create staging directory'
chmod 0700 "$STAGE"

fetch() {
  _fetch_url=$1; _fetch_dest=$2
  if [ "${BH_UPDATE_TEST_MODE:-0}" = 1 ] && [ -n "${BH_UPDATE_TEST_FETCH:-}" ]; then
    "$BH_UPDATE_TEST_FETCH" "$_fetch_url" "$_fetch_dest"
  elif command -v curl >/dev/null 2>&1; then
    curl --fail --location --silent --show-error --proto '=https' --proto-redir '=https' \
      --connect-timeout 15 --max-time 120 --output "$_fetch_dest" "$_fetch_url"
  elif command -v busybox >/dev/null 2>&1; then
    # Do NOT use --no-check-certificate. If the platform lacks TLS support, fail closed.
    busybox wget -T 30 -qO "$_fetch_dest" "$_fetch_url"
  else
    return 1
  fi
}
validate_url() {
  case "$1" in https://*) : ;; *) fail "non-HTTPS source refused" ;; esac
  case "$1" in *[!A-Za-z0-9._~:/?\&=%+#@!,\-]*|'https://'|'') fail 'invalid source URL characters' ;; esac
}
# A complete source download is mandatory. A failed or truncated source must not create a partial ruleset.
source_count=0
skipped_urls=0
: > "$STAGE/ux09-seen-urls"
fetch_sources() {
  _list=$1; _mode=$2; _dest=$3
  [ -f "$_list" ] && [ ! -L "$_list" ] || fail 'source list missing or unsafe'
  while IFS= read -r _line || [ -n "$_line" ]; do
    _line=${_line%%#*}
    _line=$(printf '%s' "$_line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    case "$_line" in ''|disabled\|*) continue ;; esac
    validate_url "$_line"
    if grep -Fqx -- "$_mode|$_line" "$STAGE/ux09-seen-urls"; then
      skipped_urls=$((skipped_urls+1))
      ux09_event SKIPPED_DUPLICATE_URL "Count $skipped_urls"
      continue
    fi
    printf '%s\n' "$_mode|$_line" >> "$STAGE/ux09-seen-urls"
    source_count=$((source_count+1))
    ux09_event DOWNLOADING "Source $source_count"
    _download="$STAGE/source.$source_count"
    printf '[>] verified HTTPS source %s\n' "$_line"
    fetch "$_line" "$_download" || fail "download failed: $_line"
    [ -s "$_download" ] || fail "empty download: $_line"
    [ "$(wc -c < "$_download")" -le 67108864 ] || fail "source exceeds 64 MiB: $_line"
    awk -v mode="$_mode" -f "$PARSE" "$_download" > "$STAGE/parsed.$source_count" || fail 'invalid downloaded hosts syntax'
    [ -s "$STAGE/parsed.$source_count" ] || fail "no valid hosts/domain entries: $_line"
    ux09_event PARSED "Source $source_count validated"
    cat "$STAGE/parsed.$source_count" >> "$_dest" || fail 'could not stage source entries'
  done < "$_list"
}

: > "$STAGE/blocked"
: > "$STAGE/allowed"
: > "$STAGE/custom"
fetch_sources "$ROOT/sources.txt" hosts "$STAGE/blocked"
[ "$source_count" -gt 0 ] || fail 'no enabled blocking sources'
fetch_sources "$ROOT/sources_whitelist.txt" allow "$STAGE/allowed"
[ -s "$STAGE/blocked" ] || fail 'download yielded no valid block entries'

[ -f "$ROOT/blacklist.txt" ] && [ ! -L "$ROOT/blacklist.txt" ] || fail 'unsafe blacklist'
[ -f "$ROOT/whitelist.txt" ] && [ ! -L "$ROOT/whitelist.txt" ] || fail 'unsafe whitelist'
awk -v mode=blacklist -f "$PARSE" "$ROOT/blacklist.txt" >> "$STAGE/blocked" || fail 'cannot read blacklist'
awk -v mode=allow -f "$PARSE" "$ROOT/whitelist.txt" >> "$STAGE/allowed" || fail 'cannot read allowlist'
for _custom in "$ROOT"/custom*.txt; do
  [ -e "$_custom" ] || continue
  [ -f "$_custom" ] && [ ! -L "$_custom" ] || fail 'unsafe custom mapping file'
  awk -v mode=custom -f "$PARSE" "$_custom" >> "$STAGE/custom" || fail 'cannot read custom mapping'
done

# Exact match only; explicit *.domain includes the base domain and all of its subdomains.
ux09_event DEDUPLICATING 'Normalizing combined blocklists'
ux09_raw=$(wc -l < "$STAGE/blocked" | tr -d ' ')
LC_ALL=C sort -u "$STAGE/blocked" > "$STAGE/block-unique"
LC_ALL=C sort -u "$STAGE/allowed" > "$STAGE/allow-unique"
ux09_unique=$(wc -l < "$STAGE/block-unique" | tr -d ' ')
ux09_dup=$((ux09_raw-ux09_unique))
ux09_event ALLOWLIST 'Applying exact and wildcard exclusions'
awk '
  FILENAME==ARGV[1] { allow[$0]=1; next }
  {
    host=$2; deny=(host in allow)
    if (!deny) {
      parts=split(host, labels, ".")
      for (i=2; i<=parts; i++) {
        suffix=labels[i]
        for(j=i+1;j<=parts;j++) suffix=suffix "." labels[j]
        if (("*." suffix) in allow) {deny=1;break}
      }
      if (("*." host) in allow) deny=1
    }
    if (!deny) print
  }
' "$STAGE/allow-unique" "$STAGE/block-unique" > "$STAGE/filtered" || fail 'allowlist reconciliation failed'

{
  printf '127.0.0.1 localhost\n::1 localhost\n'
  printf '# bindhosts-custom-start\n'
  LC_ALL=C sort -u "$STAGE/custom"
  printf '# bindhosts-custom-end\n'
  printf '# bindhosts-block-start\n'
  _response_mode=off
  if [ -f "$ROOT/response.mode" ]; then
    [ ! -L "$ROOT/response.mode" ] || fail 'unsafe response mode flag'
    _response_mode=$(cat "$ROOT/response.mode")
  fi
  case "$_response_mode" in
    off) cat "$STAGE/filtered" ;;
    logo|transparent)
      # Never redirect blocked domains to localhost if the responder is absent.
      sh "$MODDIR/response_mode.sh" "$ROOT" "$TARGET" status | grep -Fxq 'server=running' || fail 'HTTP responder not running'
      awk '$1=="0.0.0.0" && NF==2 { print "127.0.0.1",$2,"# bh-response"; next } { print }' "$STAGE/filtered" ;;
    *) fail 'invalid saved response mode' ;;
  esac
  printf '# bindhosts-block-end\n'
  printf '# bindhosts v%s\n' "$VERSION"
} > "$STAGE/candidate" || fail 'could not render candidate'
ux09_final=$(wc -l < "$STAGE/filtered" | tr -d ' ')
ux09_excluded=$((ux09_unique-ux09_final))
ux09_event GENERATING 'Candidate hosts rendered and validated'
[ -s "$STAGE/candidate" ] && grep -Fq "# bindhosts v$VERSION" "$STAGE/candidate" || fail 'candidate validation failed'
[ -s "$TARGET" ] || fail 'active hosts unexpectedly empty'
if cmp -s "$TARGET" "$STAGE/candidate"; then
  ux09_applied
  ux09_event STATS "$ux09_raw|$ux09_dup|$ux09_unique|$ux09_excluded|$ux09_final|$source_count|$skipped_urls|0"
  ux09_event UNCHANGED 'Hosts file already matches verified candidate'
  echo 'BH_UPDATE_UNCHANGED: original already up to date'; exit 0
fi
# Journaled mount-aware commit; recovery runs on boot if power is lost during
# an in-place bind-mounted write. The fallback is NOT power-loss atomic.
ux09_event COMMITTING 'Journaled writer committing verified candidate'
BH_HOSTS_ROOT="$ROOT" BH_HOSTS_TEST_MODE="${BH_UPDATE_TEST_MODE:-0}" \
  sh "$MODDIR/hosts_target_safe.sh" commit "$TARGET" "$STAGE/candidate" || fail 'journaled hosts commit failed'
ux09_applied
ux09_event STATS "$ux09_raw|$ux09_dup|$ux09_unique|$ux09_excluded|$ux09_final|$source_count|$skipped_urls|1"
ux09_event DONE 'Hosts candidate committed and verified'
echo 'BH_UPDATE_SAFE_PASS: candidate committed and verified'
