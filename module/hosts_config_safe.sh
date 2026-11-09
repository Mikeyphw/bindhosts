#!/system/bin/sh
# UX02: validated root-side config editor. No eval, sed expressions, or shell interpolation of user data.
set -eu
umask 077
ROOT=${BH_CONFIG_ROOT:-/data/adb/bindhosts}
[ "${BH_CONFIG_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || { echo 'BH_CONFIG_ERROR: root required' >&2; exit 1; }
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] || { echo 'BH_CONFIG_ERROR: unsafe state directory' >&2; exit 1; }
LOCK="$ROOT/.hosts-config.lock"
CATLOCK="$ROOT/.source-catalog.lock"
STAGEDIR="$ROOT/.hosts-editor-staging"
TMP=''; LOCKED=0; CATLOCKED=0
error() { printf 'BH_CONFIG_ERROR: %s\n' "$*" >&2; exit 1; }
cleanup() {
  [ -z "$TMP" ] || rm -f "$TMP"
  [ "$CATLOCKED" = 0 ] || rmdir "$CATLOCK" 2>/dev/null || :
  [ "$LOCKED" = 0 ] || rmdir "$LOCK" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

kind_path() {
  case "$1" in
    sources|sources_whitelist|blacklist|whitelist|custom) KIND="$1"; FILE="$ROOT/$1.txt" ;;
    custom_*.txt)
      case "$1" in *[!A-Za-z0-9_.-]*|*..*|custom_.txt) error 'invalid custom filename' ;; esac
      KIND=custom; FILE="$ROOT/$1" ;;
    *) error 'unsupported file kind' ;;
  esac
  [ ! -L "$FILE" ] || error 'refusing symbolic link'
}
lock() {
  mkdir "$LOCK" 2>/dev/null || error 'another configuration edit is running'
  LOCKED=1
  if [ "${KIND:-}" = sources ]; then
    mkdir "$CATLOCK" 2>/dev/null || error 'source catalog update is running'
    CATLOCKED=1
  fi
}
newtmp() { TMP=$(mktemp "$ROOT/.hosts-config.XXXXXXXX") || error 'cannot allocate staging file'; }
base64_to() {
  _b64=$1; _out=$2
  case "$_b64" in *[!A-Za-z0-9+/=]*) error 'invalid base64 argument' ;; esac
  printf '%s' "$_b64" | base64 -d > "$_out" || error 'base64 decoding failed'
}
read_line() {
  newtmp
  base64_to "$1" "$TMP"
  [ "$(wc -c < "$TMP")" -le 4096 ] || error 'line too long'
  # Inspect raw bytes BEFORE shell command substitution can discard NUL/LF.
  _raw_controls=$(LC_ALL=C tr -cd '\000-\037\177' < "$TMP" | wc -c) || error 'cannot inspect line bytes'
  [ "$_raw_controls" -eq 0 ] || error 'control characters not allowed'
  TEXT=$(cat "$TMP")
  [ -n "$TEXT" ] || error 'empty line'
  rm -f "$TMP"; TMP=''
}
valid_domain() { printf '%s\n' "$1" | LC_ALL=C grep -Eq '^(\*\.)?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$'; }
valid_line() {
  _line=$1
  case "$_line" in ''|\#*) return 0 ;; esac
  case "$_line" in disabled\|*) _line=${_line#disabled|} ;; esac
  # Reject leading spaces; the existing updater strips inline # comments.
  case "$_line" in ' '*|'\t'*) return 1 ;; esac
  case "$KIND" in
    sources|sources_whitelist)
      printf '%s\n' "$_line" | LC_ALL=C grep -Eq '^https://[A-Za-z0-9._~:/?&=%+#@!,-]+( #[A-Za-z0-9 _.:/-]+)?$' ;;
    whitelist|blacklist)
      _domain=${_line%% *}
      valid_domain "$_domain" && { [ "$_domain" = "$_line" ] || printf '%s\n' "${_line#* }" | LC_ALL=C grep -Eq '^#[A-Za-z0-9 _./:-]+$'; } ;;
    custom)
      # Preserve custom DNS mappings, but reject unrecognized/malformed active entries.
      printf '%s\n' "$_line" | LC_ALL=C grep -Eq '^([0-9.]+|[0-9a-fA-F:]+)[[:space:]]+[A-Za-z0-9_.-]+([[:space:]]+[A-Za-z0-9_.-]+)*([[:space:]]+#[A-Za-z0-9 _./:-]+)?$' ;;
    *) return 1 ;;
  esac
}
# Validate the entire staged file in one bounded, streaming AWK pass.
# The previous implementation forked grep for each line (1000+ subprocesses),
# exceeding the 7-second per-command timeout on Android/Termux.
validate_file() {
  _check=$1
  [ "$(wc -c < "$_check")" -le 2097152 ] || error 'file exceeds 2 MiB editor limit'
  # BusyBox awk can split input at NUL, so first reject binary controls by byte.
  # LF (012) is the only allowed ASCII control character in a file.
  _controls=$(LC_ALL=C tr -cd '\000-\011\013-\037\177' < "$_check" | wc -c) || error 'cannot inspect control bytes'
  [ "$_controls" -eq 0 ] || error 'control characters not allowed'
  LC_ALL=C awk -v kind="$KIND" '
    function domain(x) {
      return x ~ /^(\*\.)?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/
    }
    function valid(x, bare, comment, pos) {
      if (x=="" || substr(x,1,1)=="#") return 1
      if (index(x,"disabled|")==1) x=substr(x,10)
      if (x=="" || x ~ /^[[:space:]]/) return 0
      if (kind=="sources" || kind=="sources_whitelist")
        return x ~ /^https:\/\/[A-Za-z0-9._~:\/?&=%+#@!,-]+( #[A-Za-z0-9 _.:\/-]+)?$/
      if (kind=="whitelist" || kind=="blacklist") {
        pos=index(x," ")
        if (pos==0) return domain(x)
        bare=substr(x,1,pos-1)
        comment=substr(x,pos+1)
        return domain(bare) && comment ~ /^#[A-Za-z0-9 _.\/:-]+$/
      }
      if (kind=="custom")
        return x ~ /^([0-9.]+|[0-9a-fA-F:]+)[[:space:]]+[A-Za-z0-9_.-]+([[:space:]]+[A-Za-z0-9_.-]+)*([[:space:]]+#[A-Za-z0-9 _.\/:-]+)?$/
      return 0
    }
    !valid($0) { invalid=1; exit 7 }
    END {if (invalid) exit 7}
  ' "$_check" || error "invalid $KIND entry; original file unchanged"
}
commit_file() {
  [ -f "$FILE" ] && [ ! -L "$FILE" ] || error 'configuration file missing or unsafe'
  [ ! -L "$FILE" ] || error 'unsafe file'
  chmod 0644 "$TMP"
  mv -f "$TMP" "$FILE" || error 'atomic configuration replacement failed'
  TMP=''
  printf 'BH_CONFIG_COMMIT_PASS: %s\n' "${FILE##*/}"
}
line_op() {
  [ "$#" -ge 3 ] || error 'usage: line-op KIND BASE64 [BASE64]'
  kind_path "$2"; [ -f "$FILE" ] || error 'missing file'
  read_line "$3"; OLD=$TEXT
  if [ "$1" = replace ]; then
    [ "$#" -eq 4 ] || error 'replace requires two entries'
    read_line "$4"; NEW=$TEXT
    valid_line "$NEW" || error 'invalid replacement entry'
  elif [ "$1" = toggle ]; then
    case "$OLD" in disabled\|*) NEW=${OLD#disabled|} ;; *) NEW="disabled|$OLD" ;; esac
    valid_line "$NEW" || error 'invalid entry toggle'
  else
    [ "$#" -eq 3 ] || error 'unexpected arguments'
    NEW=''
    [ "$1" != add ] || valid_line "$OLD" || error 'invalid new entry'
  fi
  lock; newtmp
  case "$1" in
    add)
      if grep -Fxq "$OLD" "$FILE"; then echo 'BH_CONFIG_ALREADY_EXISTS'; return 0; fi
      cat "$FILE" > "$TMP" || error 'cannot stage config'
      printf '%s\n' "$OLD" >> "$TMP" ;;
    remove)
      grep -Fvx "$OLD" "$FILE" > "$TMP" || : ;;
    replace|toggle)
      awk -v old="$OLD" -v replacement="$NEW" '
        {if ($0==old) {n++; print replacement} else print}
        END {if(n!=1) exit 25}
      ' "$FILE" > "$TMP" || error 'entry missing or duplicated; refusing rewrite' ;;
  esac
  validate_file "$TMP"
  commit_file
}

validate_token() {
  case "$1" in ''|*[!A-Za-z0-9_-]*) error 'invalid transaction token' ;; esac
  [ "${#1}" -ge 12 ] && [ "${#1}" -le 60 ] || error 'transaction token length invalid'
}
make_staging() {
  [ ! -L "$STAGEDIR" ] || error 'unsafe staging directory'
  mkdir -p "$STAGEDIR" && chmod 0700 "$STAGEDIR" || error 'cannot secure staging directory'
}

cmd=${1:-}; [ "$#" = 0 ] || shift
case "$cmd" in
  add|remove|toggle|replace)
    line_op "$cmd" "$@" ;;
  stage-begin)
    [ "$#" -eq 1 ] || error 'stage-begin TOKEN'; validate_token "$1"
    KIND=''; lock; make_staging
    mkdir "$STAGEDIR/$1" 2>/dev/null || error 'transaction already exists'
    chmod 0700 "$STAGEDIR/$1"
    : > "$STAGEDIR/$1/content" || error 'cannot create staged content'
    echo 'BH_CONFIG_STAGE_STARTED' ;;
  stage-chunk)
    [ "$#" -eq 2 ] || error 'stage-chunk TOKEN BASE64'; validate_token "$1"
    KIND=''; lock; make_staging
    [ -d "$STAGEDIR/$1" ] && [ ! -L "$STAGEDIR/$1" ] || error 'unknown transaction'
    [ -f "$STAGEDIR/$1/content" ] && [ ! -L "$STAGEDIR/$1/content" ] || error 'unsafe transaction'
    newtmp; base64_to "$2" "$TMP"
    [ "$(wc -c < "$TMP")" -le 8192 ] || error 'chunk over 8 KiB'
    _size=$(wc -c < "$STAGEDIR/$1/content")
    [ $((_size + $(wc -c < "$TMP"))) -le 2097152 ] || error 'staged file too large'
    cat "$TMP" >> "$STAGEDIR/$1/content" || error 'append failed'
    echo 'BH_CONFIG_CHUNK_OK' ;;
  stage-commit)
    [ "$#" -eq 2 ] || error 'stage-commit TOKEN FILE_KIND'; validate_token "$1"
    _id=$1; kind_path "$2"; lock; make_staging
    [ -f "$STAGEDIR/$_id/content" ] && [ ! -L "$STAGEDIR/$_id/content" ] || error 'staging missing'
    newtmp
    cat "$STAGEDIR/$_id/content" > "$TMP" || error 'cannot stage final content'
    validate_file "$TMP"
    commit_file
    rm -rf "$STAGEDIR/$_id"
    echo 'BH_CONFIG_STAGE_COMMIT_PASS' ;;
  stage-abort)
    [ "$#" -eq 1 ] || error 'stage-abort TOKEN'; validate_token "$1"
    KIND=''; lock; make_staging
    rm -rf "$STAGEDIR/$1"; echo 'BH_CONFIG_STAGE_ABORT_PASS' ;;
  rename-custom)
    [ "$#" -eq 2 ] || error 'rename-custom OLDNAME NEWNAME'
    kind_path "$1"; [ "$KIND" = custom ] || error 'not a custom file'
    _old=$FILE; kind_path "$2"; [ "$KIND" = custom ] || error 'not a custom file'
    _new=$FILE; [ "$_old" != "$_new" ] || { echo 'BH_CONFIG_SAME_NAME'; exit 0; }
    [ -f "$_old" ] && [ ! -L "$_old" ] && [ ! -e "$_new" ] || error 'unsafe rename/target exists'
    lock; mv "$_old" "$_new" || error 'rename failed'; echo 'BH_CONFIG_RENAME_PASS' ;;
  delete-custom)
    [ "$#" -eq 1 ] || error 'delete-custom NAME'
    kind_path "$1"; [ "$KIND" = custom ] || error 'not a custom file'
    [ "$1" != custom ] && [ "$1" != custom.txt ] || error 'core custom.txt cannot be deleted'
    [ -f "$FILE" ] && [ ! -L "$FILE" ] || error 'unsafe custom file'
    lock; rm -f "$FILE" || error 'delete failed'; echo 'BH_CONFIG_DELETE_PASS' ;;
  import-custom)
    [ "$#" -eq 2 ] || error 'import-custom PATH_B64 DEST_NAME'
    kind_path "$2"; [ "$KIND" = custom ] && [ "$2" != custom ] || error 'invalid destination'
    _dst=$FILE
    read_line "$1"; _src=$TEXT
    case "$_src" in /storage/emulated/0/*|/sdcard/*) : ;; *) [ "${BH_CONFIG_TEST_MODE:-0}" = 1 ] || error 'imports must originate from shared storage' ;; esac
    case "$_src" in *..*) error 'parent traversal forbidden' ;; esac
    [ -f "$_src" ] && [ ! -L "$_src" ] && [ ! -e "$_dst" ] || error 'unsafe/missing import'
    lock; newtmp; cat "$_src" > "$TMP" || error 'cannot read import'
    validate_file "$TMP"
    chmod 0644 "$TMP"
    mv -f "$TMP" "$_dst" || error 'cannot install import'
    TMP=''; echo 'BH_CONFIG_IMPORT_PASS' ;;
  size)
    [ "$#" -eq 1 ] || error 'size FILE_KIND'; kind_path "$1"
    [ -f "$FILE" ] && [ ! -L "$FILE" ] || error 'missing file'
    wc -c < "$FILE" ;;
  *) error 'usage: add|remove|toggle|replace|stage-begin|stage-chunk|stage-commit|stage-abort|rename-custom|delete-custom|import-custom|size' ;;
esac
