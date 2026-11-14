#!/system/bin/sh
# UX09: atomic catalog selection and read-only custom-source inventory.
set -eu
umask 077
ROOT=${BH_CATALOG_ROOT:-/data/adb/bindhosts}
CAT=${BH_CATALOG_FILE:-/data/adb/modules/bindhosts/data/source-catalog.tsv}
SRC="$ROOT/sources.txt"
LOCK="$ROOT/.source-catalog.lock"
UPDATE_LOCK="$ROOT/.hosts-update.lock"
fail() { printf 'BH_UX09_CATALOG_REFUSED: %s\n' "$1" >&2; exit 1; }
[ "${BH_CATALOG_TEST_ROOT:-0}" = 1 ] || [ "$(id -u)" = 0 ] || fail 'root required'
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] && [ -f "$SRC" ] && [ ! -L "$SRC" ] && [ -f "$CAT" ] && [ ! -L "$CAT" ] || fail 'unsafe source paths'
# Defense against stale / silently changed catalog schema.
awk -F'|' '
 /^#/ || /^$/ {next}
 NF!=4 || $1 !~ /^[a-z0-9-]+$/ || $2=="" || $3 !~ /^https:\/\/[A-Za-z0-9._\/+-]+$/ || $4 !~ /^[a-z0-9-]+$/ {bad=1}
 {if (ids[$1]++ || urls[$3]++) bad=1}
 END {exit bad?1:0}
' "$CAT" || fail 'invalid shipped catalog'
case "${1:-}" in
  applied-status)
    [ "$#" -eq 1 ] || fail 'unexpected applied-status arguments'
    if [ ! -f "$ROOT/.sources-applied.sha256" ]; then echo 'BH_UX09_APPLIED=UNKNOWN'; exit 0; fi
    [ ! -L "$ROOT/.sources-applied.sha256" ] || fail 'unsafe applied fingerprint'
    stored=$(cat "$ROOT/.sources-applied.sha256")
    case "$stored" in *[!0-9a-f]*|'') fail 'corrupt applied fingerprint' ;; esac
    [ "${#stored}" -eq 64 ] || fail 'invalid fingerprint length'
    current=$(sha256sum "$SRC" | awk '{print $1}') || fail 'cannot hash sources'
    if [ "$stored" = "$current" ]; then echo 'BH_UX09_APPLIED=CURRENT'; else echo 'BH_UX09_APPLIED=PENDING'; fi
    if [ -f "$ROOT/.sources-applied.epoch" ]; then
      [ ! -L "$ROOT/.sources-applied.epoch" ] || fail 'unsafe validation timestamp'
      stamp=$(cat "$ROOT/.sources-applied.epoch")
      case "$stamp" in ''|*[!0-9]*) fail 'invalid validation timestamp' ;; esac
      printf 'BH_UX09_LAST_APPLIED_EPOCH=%s\n' "$stamp"
    fi
    ;;
  manual-list)
    [ "$#" -eq 1 ] || fail 'unexpected manual-list arguments'
    LC_ALL=C awk '
      /^[[:space:]]*$/ || /^[[:space:]]*#/ {next}
      / # source-catalog:[a-z0-9-]+$/ {next}
      {
        raw=$0; active="on"; line=$0
        if (index(line,"disabled|")==1) {active="off"; sub(/^disabled\|/,"",line)}
        sub(/[[:space:]]*#.*/, "", line);gsub(/^[[:space:]]+|[[:space:]]+$/,"",line)
        if (line ~ /^https:\/\// && length(raw)<2000) print "MANUAL|" active "|" raw
      }
    ' "$SRC"
    ;;
  batch)
    [ "$#" -eq 2 ] || fail 'batch requires comma-separated preset IDs or none'
    selected=$2
    case "$selected" in none) selected='' ;; *[!a-z0-9,-]*|,*|*,|*,,*) fail 'invalid preset selection' ;; esac
    # Validate entire requested set, Energized exclusivity, before any mutation.
    printf '%s\n' "$selected" | awk -F, 'NF>30{exit 3} {for(i=1;i<=NF;i++) if($i!="" && seen[$i]++) exit 3}' || fail 'duplicate preset IDs'
    awk -F'|' -v selected="$selected" '
      BEGIN { n=split(selected,p,","); for(i=1;i<=n;i++) if(p[i]!="") {want[p[i]]=1; count++} }
      /^#/ || /^$/ {next}
      {known[$1]=1; if(($1 in want) && $4=="energized") eng++}
      END {if(eng>1) exit 2; for(id in want) if(!(id in known)) exit 3}
    ' "$CAT" || fail 'unknown preset or multiple Energized tiers'
    mkdir "$LOCK" 2>/dev/null || fail 'source catalog editor is busy'
    GOT=1; UP=0; TMP=''
    cleanup() { [ -z "$TMP" ] || rm -f "$TMP"; [ "$UP" = 0 ] || rmdir "$UPDATE_LOCK" 2>/dev/null || :; [ "$GOT" = 0 ] || rmdir "$LOCK" 2>/dev/null || :; }
    trap cleanup EXIT
    # The journaled updater holds this lock from initial reading until commit.
    mkdir "$UPDATE_LOCK" 2>/dev/null || fail 'hosts update in progress'
    UP=1
    [ ! -L "$SRC" ] && [ -f "$SRC" ] || fail 'source file changed unsafely'
    TMP=$(mktemp "$ROOT/.ux09-sources.XXXXXXXX") || fail 'cannot stage sources'
    chmod 0600 "$TMP"
    LC_ALL=C awk -v selected="$selected" -v catalog="$CAT" '
      BEGIN {
        FS="|"; n=split(selected,p,","); for(i=1;i<=n;i++) if(p[i]!="") want[p[i]]=1
        while((getline row < catalog)>0) {split(row,v,"|"); if(v[1] ~ /^[a-z0-9-]+$/) {urls[v[1]]=v[3]; ids[++count]=v[1]}}
        close(catalog)
      }
      {
        original=$0; clean=$0
        sub(/^[[:space:]]*/,"",clean);sub(/^disabled\|/,"",clean)
        sub(/[[:space:]]*#.*/,"",clean);sub(/[[:space:]]*$/, "",clean)
        # Preserve manually managed entries, even if URL matches a preset.
        if(match(original, / # source-catalog:[a-z0-9-]+$/)) {
          id=substr(original,RSTART+18)
          if((id in urls) && clean==urls[id]) next
        }
        if(clean ~ /^https:\/\// && index(original,"disabled|")!=1) foreign[clean]=1
        print original
      }
      END {for(i=1;i<=count;i++) {id=ids[i]; if((id in want) && !(urls[id] in foreign)) print urls[id] " # source-catalog:" id}}
    ' "$SRC" > "$TMP" || fail 'batch construction failed'
    cmp -s "$SRC" "$TMP" && { echo 'BH_UX09_BATCH_UNCHANGED'; exit 0; }
    mv -f "$TMP" "$SRC" || fail 'atomic source replacement failed'
    TMP=''; chmod 0600 "$SRC"
    echo 'BH_UX09_BATCH_APPLIED'
    ;;
  *) fail 'usage: applied-status|manual-list|batch SELECTION' ;;
esac
