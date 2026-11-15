#!/system/bin/sh
# BH-APP01 P04B P02: finite, read-only, fingerprint-pinned paginated responses.
# The caller provides a base64 *data* token, never a shell command or path.
set -eu
set -f
umask 077
refuse() { printf 'BH_APP01_V4_REFUSED: %s\n' "$1" >&2; exit 2; }
[ "$#" -eq 1 ] || refuse 'expected exactly one base64 request'
TOKEN=$1
case "$TOKEN" in ''|*[!A-Za-z0-9+/=]*) refuse 'invalid request encoding' ;; esac
[ "${#TOKEN}" -le 480 ] || refuse 'request too long'
# Inspect raw decoded bytes before shell substitution can discard NUL/controls.
CONTROL_BYTES=$(printf '%s' "$TOKEN" | base64 -d 2>/dev/null | LC_ALL=C tr -cd '\000-\037\177' | wc -c) || refuse 'invalid request bytes'
case "$CONTROL_BYTES" in ''|*[!0-9]*) refuse 'invalid control-byte count' ;; esac
[ "$CONTROL_BYTES" -eq 0 ] || refuse 'control characters in encoded input'
REQUEST=$(printf '%s' "$TOKEN" | base64 -d 2>/dev/null) || refuse 'decode refused'
case "$REQUEST" in *[!A-Za-z0-9_.~|=-]*|'') refuse 'invalid request charset' ;; esac
OLDIFS=$IFS; IFS='|'; set -- $REQUEST; IFS=$OLDIFS
[ "$#" -eq 4 ] || refuse 'expected source, selection, offset, digest'
SOURCE=$1; SELECTOR=$2; OFFSET=$3; EXPECT=$4
case "$SOURCE" in config-read|config-list|catalog|tracker|packages|backup|diagnostics|response) : ;; *) refuse 'unsupported read source' ;; esac
case "$OFFSET" in ''|*[!0-9]*) refuse 'invalid page offset' ;; esac
[ "${#OFFSET}" -le 6 ] || refuse 'invalid offset length'
[ "$OFFSET" -le 262144 ] || refuse 'out-of-range page offset'
case "$EXPECT" in none) : ;; *) case "$EXPECT" in *[!0-9a-f]*) refuse 'invalid expected digest' ;; esac
  [ "${#EXPECT}" -eq 64 ] || refuse 'invalid digest length' ;; esac
case "$SELECTOR" in ''|*[!A-Za-z0-9_.~-]*|*..*) refuse 'invalid selector' ;; esac
[ "${#SELECTOR}" -le 110 ] || refuse 'oversized selector'
if [ "${BH_APP01_V4_TEST_MODE:-0}" = 1 ]; then
  [ "$(id -u)" -ne 0 ] || refuse 'rooted fixture refused'
  MODDIR=${BH_APP01_V4_TEST_MODDIR:-}; STATE=${BH_APP01_V4_TEST_STATE:-}
  [ -n "$MODDIR" ] && [ -n "$STATE" ] || refuse 'incomplete fixture'
else
  [ -z "${BH_APP01_V4_TEST_MODDIR:-}" ] && [ -z "${BH_APP01_V4_TEST_STATE:-}" ] || refuse 'fixture override in production'
  [ "$(id -u)" = 0 ] || refuse 'root required'
  MODDIR=/data/adb/modules/bindhosts; STATE=/data/adb/bindhosts
fi
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] && [ -d "$STATE" ] && [ ! -L "$STATE" ] || refuse 'unsafe module or state'
require_backend() { [ -f "$MODDIR/$1" ] && [ ! -L "$MODDIR/$1" ] || refuse 'unsafe read backend'; }
config_path() {
  case "$1" in
    sources|sources_whitelist|blacklist|whitelist|custom) TARGET="$STATE/$1.txt" ;;
    custom_*.txt) case "$1" in *[!A-Za-z0-9_.-]*|*..*|custom_.txt) refuse 'invalid custom filename' ;; esac; TARGET="$STATE/$1" ;;
    *) refuse 'invalid config read kind' ;;
  esac
  [ -f "$TARGET" ] && [ ! -L "$TARGET" ] || refuse 'unsafe or missing config file'
}
# Temp is created inside the module's private state directory with mode 0600.
# Each request re-generates a snapshot, then checks its digest against the
# previous page's digest. Concurrent changes therefore fail closed.
TMP=$(mktemp "$STATE/.bh-app01-v4.XXXXXXXX") || refuse 'temp allocation failed'
trap 'rm -f "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
case "$SOURCE" in
  config-read)
    config_path "$SELECTOR"
    cat "$TARGET" > "$TMP" || refuse 'config read failed' ;;
  config-list)
    [ "$SELECTOR" = custom ] || refuse 'unsupported file listing'
    for f in "$STATE"/custom_*.txt; do
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      name=${f##*/}
      case "$name" in *[!A-Za-z0-9_.-]*|*..*|custom_.txt) continue ;; esac
      printf '%s\n' "$name"
    done | LC_ALL=C sort > "$TMP" || refuse 'list failed' ;;
  catalog)
    case "$SELECTOR" in
      status) require_backend source_catalog.sh; sh "$MODDIR/source_catalog.sh" status > "$TMP" 2>/dev/null || refuse 'catalog status refused' ;;
      applied-status|manual-list) require_backend source_catalog_batch_ux09.sh
        sh "$MODDIR/source_catalog_batch_ux09.sh" "$SELECTOR" > "$TMP" 2>/dev/null || refuse 'catalog read refused' ;;
      *) refuse 'unsupported catalog read' ;;
    esac ;;
  tracker)
    require_backend bindhosts.sh
    case "$SELECTOR" in
      status|rules) sh "$MODDIR/bindhosts.sh" tracker json "$SELECTOR" > "$TMP" 2>/dev/null || refuse 'tracker read refused' ;;
      preview~*)
        PKG=${SELECTOR#preview~}
        case "$PKG" in ''|.*|*.|*[!A-Za-z0-9_.]*|*..*) refuse 'invalid package' ;; esac
        printf '%s' "$PKG" | LC_ALL=C grep -Eq '^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$' || refuse 'invalid package name'
        sh "$MODDIR/bindhosts.sh" tracker preview "$PKG" > "$TMP" 2>/dev/null || refuse 'tracker preview refused' ;;
      *) refuse 'unsupported tracker read' ;;
    esac ;;
  packages)
    [ "$SELECTOR" = user ] || refuse 'unsupported package inventory'
    pm list packages -3 > "$TMP" 2>/dev/null || refuse 'package read refused' ;;
  backup)
    require_backend config_backup_safe.sh
    case "$SELECTOR" in
      status|health|list|imports)
        sh "$MODDIR/config_backup_safe.sh" "$SELECTOR" > "$TMP" 2>/dev/null || refuse 'backup read refused' ;;
      verify~*|preview~*)
        VERB=${SELECTOR%%~*}; SNAP=${SELECTOR#*~}
        printf '%s' "$SNAP" | LC_ALL=C grep -Eq '^bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$' || refuse 'invalid backup snapshot'
        sh "$MODDIR/config_backup_safe.sh" "$VERB" "$SNAP" > "$TMP" 2>/dev/null || refuse 'backup verification refused' ;;
      *) refuse 'unsupported backup read' ;;
    esac ;;
  diagnostics)
    require_backend ux05_diagnostics.sh
    case "$SELECTOR" in
      status) sh "$MODDIR/ux05_diagnostics.sh" status > "$TMP" 2>/dev/null || refuse 'diagnostics status refused' ;;
      history~*)
        LIMIT=${SELECTOR#history~}
        case "$LIMIT" in ''|*[!0-9]*) refuse 'invalid diagnostics history limit' ;; esac
        [ "${#LIMIT}" -le 3 ] && [ "$LIMIT" -ge 1 ] && [ "$LIMIT" -le 100 ] || refuse 'out-of-range history limit'
        sh "$MODDIR/ux05_diagnostics.sh" history "$LIMIT" > "$TMP" 2>/dev/null || refuse 'diagnostics history refused' ;;
      *) refuse 'unsupported diagnostics read' ;;
    esac ;;
  response)
    require_backend bindhosts.sh
    [ "$SELECTOR" = status ] || refuse 'unsupported response read'
    sh "$MODDIR/bindhosts.sh" --response status > "$TMP" 2>/dev/null || refuse 'blocked response status refused' ;;
esac
SIZE=$(wc -c < "$TMP" | tr -d ' ')
case "$SIZE" in ''|*[!0-9]*) refuse 'invalid read size' ;; esac
[ "$SIZE" -le 262144 ] || refuse 'read exceeds 256 KiB cap'
[ "$OFFSET" -le "$SIZE" ] || refuse 'offset beyond read size'
SHA=$(sha256sum "$TMP" | cut -d' ' -f1) || refuse 'cannot hash read snapshot'
case "$SHA" in *[!0-9a-f]*|'') refuse 'invalid snapshot hash' ;; esac
[ "${#SHA}" -eq 64 ] || refuse 'invalid snapshot digest'
[ "$EXPECT" = none ] || [ "$EXPECT" = "$SHA" ] || refuse 'snapshot changed during pagination'
PAGE=3072
REMAIN=$((SIZE-OFFSET))
if [ "$REMAIN" -gt "$PAGE" ]; then COUNT=$PAGE; NEXT=$((OFFSET+PAGE)); else COUNT=$REMAIN; NEXT=null; fi
# Head/tail are invoked on private bounded files; only page bytes leave stdout.
if [ "$COUNT" -gt 0 ]; then
  ENC=$(tail -c +$((OFFSET+1)) "$TMP" | head -c "$COUNT" | base64 | tr -d '\r\n') || refuse 'page encoding failed'
else ENC=''; fi
case "$ENC" in *[!A-Za-z0-9+/=]*) refuse 'invalid response encoding' ;; esac
printf '{"api":4,"action":"read-page","source":"%s","selector":"%s","offset":%s,"next":%s,"size":%s,"sha256":"%s","encoded":"%s"}\n' \
  "$SOURCE" "$SELECTOR" "$OFFSET" "$NEXT" "$SIZE" "$SHA" "$ENC"
