#!/system/bin/sh
# SPDX-License-Identifier: MIT
# UX01: narrowly scoped, root-only hosts catalog manager. Never evaluates client input.
set -eu
umask 077

ROOT=${BH_CATALOG_ROOT:-/data/adb/bindhosts}
CAT=${BH_CATALOG_FILE:-/data/adb/modules/bindhosts/data/source-catalog.tsv}
SRC=$ROOT/sources.txt
LOCK=$ROOT/.source-catalog.lock
TMP=''
OWN='source-catalog:'

fail() { printf 'CATALOG_ERROR: %s\n' "$*" >&2; exit 1; }
[ "${BH_CATALOG_TEST_ROOT:-0}" = 1 ] || [ "$(id -u)" = 0 ] || fail 'root required'
[ -f "$CAT" ] && [ ! -L "$CAT" ] || fail 'missing/unsafe catalog'
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] || fail 'missing/unsafe state directory'
[ -f "$SRC" ] && [ ! -L "$SRC" ] || fail 'missing/unsafe sources file'

# Validate the shipped catalog itself, including the absence of duplicate IDs/URLs.
awk -F'|' '
  /^#/ || /^$/ {next}
  NF!=4 || $1 !~ /^[a-z0-9-]+$/ || $2=="" || $3 !~ /^https:\/\/[A-Za-z0-9._\/+-]+$/ || $4 !~ /^[a-z0-9-]+$/ {bad=1}
  {if (ids[$1]++ || urls[$3]++) bad=1}
  END {exit bad ? 1 : 0}
' "$CAT" || fail 'catalog data invalid'

cleanup() {
  [ -z "$TMP" ] || rm -f "$TMP"
  [ "${LOCKED:-0}" = 1 ] && rmdir "$LOCK" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

get_preset() {
  ID=$1
  case "$ID" in ''|*[!a-z0-9-]*) fail 'invalid preset ID' ;; esac
  REC=$(awk -F'|' -v id="$ID" '$1==id && NF==4 { print; found=1; exit } END{if(!found) exit 2}' "$CAT") || fail 'unknown preset'
  URL=$(printf '%s\n' "$REC" | cut -d'|' -f3)
  GROUP=$(printf '%s\n' "$REC" | cut -d'|' -f4)
}

# Classifies a URL as on (catalog-owned), external (user-owned), or off.
# Never alters manually configured sources with identical URLs.
source_state() {
  awk -v url="$1" -v id="$2" '
  {
    raw=$0; t=raw
    sub(/^[[:space:]]*/, "",t)
    active=1
    if(index(t,"disabled|")==1){sub(/^disabled\|/,"",t); active=0}
    sub(/[[:space:]]*#.*/, "",t)
    sub(/[[:space:]]*$/, "",t)
    if(t!=url || !active) next
    if(index(raw,"# source-catalog:" id)>0) ours=1; else foreign=1
  }
  END {print foreign ? "external" : (ours ? "on" : "off")}
  ' "$SRC"
}

lock_source() {
  mkdir "$LOCK" 2>/dev/null || fail 'catalog editor is locked'
  LOCKED=1
  [ ! -L "$SRC" ] && [ -f "$SRC" ] || fail 'sources changed to an unsafe file'
  TMP=$(mktemp "$ROOT/.sources-catalog.XXXXXXXX") || fail 'cannot stage configuration'
  chmod 0600 "$TMP"
}

edit_managed() {
  action=$1; id=$2; url=$3; group=$4
  # Do not delete user-created entries. Only remove our own exact catalog markers.
  awk -v id="$id" -v url="$url" -v group="$group" -v mode="$action" -v cat="$CAT" '
    BEGIN {
      FS="|"
      if(group=="energized") {
        while((getline line < cat)>0) {
          split(line,p,"|")
          if(p[4]=="energized") {peers[p[1]]=1; preseturl[p[1]]=p[3]}
        }
        close(cat)
      }
    }
    {
      raw=$0
      # Only recognize a canonical exact marker at the end.
      marker=""; if(match(raw, / # source-catalog:[a-z0-9-]+$/)) marker=substr(raw,RSTART+18)
      # The prefix is " # source-catalog:" (18 chars).
      clean=raw
      sub(/^[[:space:]]*/, "", clean)
      sub(/^disabled\|/, "", clean)
      sub(/[[:space:]]*#.*/, "", clean)
      sub(/[[:space:]]*$/, "", clean)
      if(marker==id && clean==url) next
      if(mode=="enable" && group=="energized" && (marker in peers) && clean==preseturl[marker]) next
      print raw
    }
    END { if(mode=="enable") print url " # source-catalog:" id }
  ' "$SRC" > "$TMP" || fail 'source update failed'
}

command=${1:-}
case "$command" in
  status)
    [ "$#" -eq 1 ] || fail 'usage: status'
    while IFS='|' read -r id name url group; do
      case "$id" in ''|\#*) continue ;; esac
      printf '%s|%s\n' "$id" "$(source_state "$url" "$id")"
    done < "$CAT" ;;
  enable|disable)
    [ "$#" -eq 2 ] || fail 'usage: enable|disable PRESET_ID'
    get_preset "$2"
    lock_source
    current=$(source_state "$URL" "$ID")
    if [ "$current" = external ]; then
      fail 'source already configured manually; manage it in the existing source editor'
    fi
    if [ "$command" = disable ] && [ "$current" = off ]; then
      printf '%s\n' "CATALOG_ALREADY_OFF: $ID"; exit 0
    fi
    edit_managed "$command" "$ID" "$URL" "$GROUP"
    [ ! -L "$SRC" ] || fail 'source file replaced during transaction'
    mv -f "$TMP" "$SRC" || fail 'commit failed'
    TMP=''
    chmod 0600 "$SRC"
    printf '%s\n' "CATALOG_${command}: $ID (hosts update not run)" ;;
  *) fail 'usage: status|enable PRESET_ID|disable PRESET_ID' ;;
esac
