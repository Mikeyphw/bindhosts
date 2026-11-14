#!/system/bin/sh
# BH-APP01 P04B: finite, rooted native mapping of existing UX02/UX09/R2 backends.
# Never eval or execute a caller-provided command. Payload is ONE base64 token.
set -eu
set -f
umask 077
refuse() { printf 'BH_APP01_V3_REFUSED: %s\n' "$1" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse 'expected verb and encoded args'
VERB=$1; INPUT=$2
case "$VERB" in config-read|config-list|config-write|catalog|tracker|packages) : ;; *) refuse 'unknown operation' ;; esac
case "$INPUT" in *[!A-Za-z0-9+/=]*|'') refuse 'malformed encoded arguments' ;; esac
[ "${#INPUT}" -le 18000 ] || refuse 'oversized argument'
ARGS=$(printf '%s' "$INPUT" | base64 -d 2>/dev/null) || refuse 'invalid base64 argument'
[ "${#ARGS}" -le 13000 ] || refuse 'oversized decoded argument'
case "$ARGS" in *[!A-Za-z0-9_.+/=,\|-]*|*..*) refuse 'invalid argument charset' ;; esac
# Fixture overrides may be supplied ONLY by a nonroot test process.
if [ "${BH_APP01_V3_TEST_MODE:-0}" = 1 ]; then
    [ "$(id -u)" -ne 0 ] || refuse 'rooted fixture refused'
    MODDIR=${BH_APP01_V3_TEST_MODDIR:-}; STATE=${BH_APP01_V3_TEST_STATE:-}
    [ -n "$MODDIR" ] && [ -n "$STATE" ] || refuse 'missing fixture paths'
else
    [ -z "${BH_APP01_V3_TEST_MODDIR:-}" ] && [ -z "${BH_APP01_V3_TEST_STATE:-}" ] || refuse 'unsafe override'
    MODDIR=/data/adb/modules/bindhosts; STATE=/data/adb/bindhosts
    [ "$(id -u)" = 0 ] || refuse 'root required'
fi
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] && [ -d "$STATE" ] && [ ! -L "$STATE" ] || refuse 'module or state unavailable'
# Split only the validated pipe delimiters. IFS is restored, never sourced/evaluated.
oldifs=$IFS; IFS='|'; set -- $ARGS; IFS=$oldifs
[ "$#" -ge 1 ] && [ "$#" -le 4 ] || refuse 'invalid argument arity'
kind() {
  case "$1" in sources|sources_whitelist|blacklist|whitelist|custom) FILE="$STATE/$1.txt" ;;
    custom_*.txt) case "$1" in *[!A-Za-z0-9_.-]*|*..*|custom_.txt) refuse 'invalid custom name' ;; esac; FILE="$STATE/$1" ;;
    *) refuse 'unsupported config kind' ;; esac
  [ ! -L "$FILE" ] || refuse 'unsafe config symlink'
}
requirefile() { [ -f "$MODDIR/$1" ] && [ ! -L "$MODDIR/$1" ] || refuse 'unsafe backend'; }
OUT=''
case "$VERB" in
  config-read)
    [ "$#" -eq 1 ] || refuse 'config-read requires kind'
    kind "$1"; [ -f "$FILE" ] || refuse 'configuration unavailable'
    [ "$(wc -c < "$FILE")" -le 4800 ] || refuse 'configuration too large for bounded read'
    OUT=$(cat "$FILE") || refuse 'configuration read failed'
    ;;
  config-list)
    [ "$#" -eq 1 ] && [ "$1" = custom ] || refuse 'only custom-list allowed'
    OUT=$(for f in "$STATE"/custom_*.txt; do
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      name=${f##*/}
      case "$name" in *[!A-Za-z0-9_.-]*|*..*|custom_.txt) continue ;; esac
      printf '%s\n' "$name"
    done | LC_ALL=C sort | head -n 80) || refuse 'listing failed'
    ;;
  config-write)
    [ "$#" -ge 2 ] || refuse 'config operation incomplete'
    OP=$1; shift
    requirefile hosts_config_safe.sh
    case "$OP" in
      add|remove|toggle) [ "$#" -eq 2 ] || refuse 'invalid line operation'; kind "$1"; [ "${#2}" -le 6000 ] || refuse 'oversized line';;
      replace) [ "$#" -eq 3 ] || refuse 'invalid replace'; kind "$1"; [ "${#2}" -le 6000 ] && [ "${#3}" -le 6000 ] || refuse 'oversized entries';;
      stage-begin|stage-abort) [ "$#" -eq 1 ] || refuse 'stage token required';;
      stage-chunk|stage-commit) [ "$#" -eq 2 ] || refuse 'invalid stage operation';;
      delete-custom) [ "$#" -eq 1 ] || refuse 'custom file required'; kind "$1"; case "$1" in custom_*.txt) : ;; *) refuse 'core configuration cannot be deleted' ;; esac;;
      rename-custom|import-custom) [ "$#" -eq 2 ] || refuse 'invalid custom operation'; case "$OP" in rename-custom) kind "$1"; case "$1" in custom_*.txt) : ;; *) refuse 'invalid rename source' ;; esac;; esac; kind "$2"; case "$2" in custom_*.txt) : ;; *) refuse 'invalid destination custom file' ;; esac;;
      *) refuse 'unsupported configuration verb' ;;
    esac
    OUT=$(sh "$MODDIR/hosts_config_safe.sh" "$OP" "$@" 2>/dev/null) || refuse 'safe config backend rejected request'
    case "$OUT" in BH_CONFIG_COMMIT_PASS:*|BH_CONFIG_ALREADY_EXISTS|BH_CONFIG_STAGE_STARTED|BH_CONFIG_CHUNK_OK|BH_CONFIG_STAGE_COMMIT_PASS|BH_CONFIG_STAGE_ABORT_PASS|BH_CONFIG_DELETE_PASS|BH_CONFIG_RENAME_PASS|BH_CONFIG_IMPORT_PASS|BH_CONFIG_SAME_NAME) : ;; *) refuse 'config success receipt missing' ;; esac
    ;;
  catalog)
    requirefile source_catalog.sh; requirefile source_catalog_batch_ux09.sh
    case "$1" in
      status) [ "$#" -eq 1 ] || refuse 'catalog status args'; OUT=$(sh "$MODDIR/source_catalog.sh" status 2>/dev/null) || refuse 'catalog status failed';;
      applied-status|manual-list) [ "$#" -eq 1 ] || refuse 'catalog read args'; OUT=$(sh "$MODDIR/source_catalog_batch_ux09.sh" "$1" 2>/dev/null) || refuse 'catalog read failed';;
      batch) [ "$#" -eq 2 ] || refuse 'batch selection required'; case "$2" in none|*[!a-z0-9,-]*) [ "$2" = none ] || refuse 'invalid batch selection' ;; esac
        OUT=$(sh "$MODDIR/source_catalog_batch_ux09.sh" batch "$2" 2>/dev/null) || refuse 'atomic source batch refused'
        case "$OUT" in BH_UX09_BATCH_APPLIED|BH_UX09_BATCH_UNCHANGED) : ;; *) refuse 'batch receipt missing' ;; esac;;
      *) refuse 'unsupported catalog action' ;;
    esac
    ;;
  tracker)
    requirefile bindhosts.sh
    case "$1" in
      status|rules) [ "$#" -eq 1 ] || refuse 'tracker JSON args'; OUT=$(sh "$MODDIR/bindhosts.sh" tracker json "$1" 2>/dev/null) || refuse 'tracker JSON unavailable';;
      preview) [ "$#" -eq 2 ] || refuse 'preview package required'; case "$2" in *[!A-Za-z0-9_.]*|''|.*|*.) refuse 'invalid package' ;; esac
        OUT=$(sh "$MODDIR/bindhosts.sh" tracker preview "$2" 2>/dev/null) || refuse 'tracker preview unavailable';;
      enroll|unenroll|exclude|include) [ "$#" -eq 2 ] || refuse 'package required'; case "$2" in *[!A-Za-z0-9_.]*|''|.*|*.) refuse 'invalid package' ;; esac
        OUT=$(sh "$MODDIR/bindhosts.sh" tracker "$1" "$2" 2>/dev/null) || refuse 'tracker write refused';;
      monitor) [ "$#" -eq 2 ] || refuse 'monitor mode required'; case "$2" in enable|disable|once) : ;; *) refuse 'invalid monitor mode' ;; esac
        OUT=$(sh "$MODDIR/bindhosts.sh" tracker monitor "$2" 2>/dev/null) || refuse 'monitor refused';;
      *) refuse 'unsupported tracker action' ;;
    esac
    ;;
  packages)
    [ "$#" -eq 1 ] && [ "$1" = user ] || refuse 'user packages only'
    OUT=$(pm list packages -3 2>/dev/null) || refuse 'package inventory unavailable'
    ;;
esac
[ "$(printf '%s' "$OUT" | wc -c)" -le 4800 ] || refuse 'result too large for bounded native bridge'
# stdout is a single JSON object; no raw content is logged or exported.
ENC=$(printf '%s' "$OUT" | base64 | tr -d '\r\n') || refuse 'base64 response failed'
case "$ENC" in *[!A-Za-z0-9+/=]*) refuse 'encoded response invalid' ;; esac
printf '{"api":3,"action":"%s","encoded":"%s"}\n' "$VERB" "$ENC"
