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
fetch_sources() {
  _list=$1; _mode=$2; _dest=$3
  [ -f "$_list" ] && [ ! -L "$_list" ] || fail 'source list missing or unsafe'
  while IFS= read -r _line || [ -n "$_line" ]; do
    _line=${_line%%#*}
    _line=$(printf '%s' "$_line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    case "$_line" in ''|disabled\|*) continue ;; esac
    validate_url "$_line"
    source_count=$((source_count+1))
    _download="$STAGE/source.$source_count"
    printf '[>] verified HTTPS source %s\n' "$_line"
    fetch "$_line" "$_download" || fail "download failed: $_line"
    [ -s "$_download" ] || fail "empty download: $_line"
    [ "$(wc -c < "$_download")" -le 67108864 ] || fail "source exceeds 64 MiB: $_line"
    awk -v mode="$_mode" -f "$PARSE" "$_download" > "$STAGE/parsed.$source_count" || fail 'invalid downloaded hosts syntax'
    [ -s "$STAGE/parsed.$source_count" ] || fail "no valid hosts/domain entries: $_line"
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
LC_ALL=C sort -u "$STAGE/blocked" > "$STAGE/block-unique"
LC_ALL=C sort -u "$STAGE/allowed" > "$STAGE/allow-unique"
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
  LC_ALL=C sort -u "$STAGE/custom"
  cat "$STAGE/filtered"
  printf '# bindhosts v%s\n' "$VERSION"
} > "$STAGE/candidate" || fail 'could not render candidate'
[ -s "$STAGE/candidate" ] && grep -Fq "# bindhosts v$VERSION" "$STAGE/candidate" || fail 'candidate validation failed'
[ -s "$TARGET" ] || fail 'active hosts unexpectedly empty'
if cmp -s "$TARGET" "$STAGE/candidate"; then
  echo 'BH_UPDATE_UNCHANGED: original already up to date'; exit 0
fi
# Save old bytes before committing. For bind-mounted /system/etc/hosts a same-dir rename
# may fail with EBUSY; in that case perform a verified write with rollback on failure.
cp -p "$TARGET" "$STAGE/previous" || fail 'could not back up active hosts'
_mode=$(stat -c %a "$TARGET" 2>/dev/null || echo 644)
_uid=$(stat -c %u "$TARGET" 2>/dev/null || echo 0)
_gid=$(stat -c %g "$TARGET" 2>/dev/null || echo 0)
case "$_mode" in ''|*[!0-7]*) _mode=644 ;; esac
NEXT_TARGET="${TARGET}.ux02.$$"
if cp "$STAGE/candidate" "$NEXT_TARGET" 2>/dev/null; then
  chmod "$_mode" "$NEXT_TARGET" 2>/dev/null || :
  chown "$_uid:$_gid" "$NEXT_TARGET" 2>/dev/null || :
  if mv -f "$NEXT_TARGET" "$TARGET" 2>/dev/null; then
    NEXT_TARGET=''
    command -v restorecon >/dev/null 2>&1 && restorecon "$TARGET" >/dev/null 2>&1 || :
    echo 'BH_UPDATE_ATOMIC_PASS: complete validated hosts committed'
    exit 0
  fi
  rm -f "$NEXT_TARGET"; NEXT_TARGET=''
fi
# Fallback for system/bind mounts that disallow renaming the active hosts file.
echo 'BH_UPDATE_FALLBACK: target disallows atomic rename; using verified write and rollback' >&2
if cat "$STAGE/candidate" > "$TARGET" && cmp -s "$STAGE/candidate" "$TARGET"; then
  echo 'BH_UPDATE_VERIFIED_PASS: complete hosts written to bound target'
  exit 0
fi
if ! cat "$STAGE/previous" > "$TARGET" || ! cmp -s "$STAGE/previous" "$TARGET"; then
  echo 'BH_UPDATE_RESTORE_FAILED: manual recovery required from saved sources' >&2
  exit 2
fi
fail 'write failed; previous hosts bytes restored'
