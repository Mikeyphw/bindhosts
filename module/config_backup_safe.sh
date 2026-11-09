#!/system/bin/sh
# UX06: root-only fixed-file snapshots. No dynamic shell commands or arbitrary paths.
set -eu
umask 077
ROOT=${BH_BACKUP_ROOT:-/data/adb/bindhosts}
MODDIR=${BH_BACKUP_MODDIR:-/data/adb/modules/bindhosts}
BACKUPS="$ROOT/.ux06-backups"
PENDING="$ROOT/.ux06-restore-pending"
DOWNLOAD=${BH_BACKUP_DOWNLOAD:-/storage/emulated/0/Download}
FILES='sources.txt sources_whitelist.txt blacklist.txt whitelist.txt custom.txt'
[ "${BH_BACKUP_TEST_MODE:-0}" = 1 ] || [ "$(id -u)" = 0 ] || { echo 'BH_BACKUP_ERROR: root required' >&2; exit 1; }
[ -d "$ROOT" ] && [ ! -L "$ROOT" ] || { echo 'BH_BACKUP_ERROR: unsafe state directory' >&2; exit 1; }

error() { printf 'BH_BACKUP_ERROR: %s\n' "$*" >&2; exit 1; }
valid_id() {
  case "$1" in bh-????????T??????-??????) : ;; *) error 'invalid snapshot id' ;; esac
  case "$1" in *[!A-Za-z0-9_-]*|*..*|*/*) error 'invalid snapshot characters' ;; esac
}
secure_dir() {
  [ ! -L "$BACKUPS" ] || error 'symlinked backup directory'
  [ -d "$BACKUPS" ] || mkdir -m 0700 "$BACKUPS" || error 'backup storage unavailable'
  chmod 0700 "$BACKUPS" || error 'cannot secure backup directory'
}
ensure_source() {
  [ -f "$ROOT/$1" ] && [ ! -L "$ROOT/$1" ] || error "unsafe or missing config $1"
}
lock_config() {
  mkdir "$ROOT/.hosts-config.lock" 2>/dev/null || error 'configuration editor busy'
  OWN_CONFIG=1
  mkdir "$ROOT/.source-catalog.lock" 2>/dev/null || error 'source catalog busy'
  OWN_CATALOG=1
}
OWN_CONFIG=0; OWN_CATALOG=0; OWN_BACKUP=0; SCRATCH=''; FAILED=0
cleanup() {
  [ -z "$SCRATCH" ] || rm -rf "$SCRATCH"
  [ "$OWN_CATALOG" -eq 0 ] || rmdir "$ROOT/.source-catalog.lock" 2>/dev/null || :
  [ "$OWN_CONFIG" -eq 0 ] || rmdir "$ROOT/.hosts-config.lock" 2>/dev/null || :
  [ "$OWN_BACKUP" -eq 0 ] || rmdir "$BACKUPS/.lock" 2>/dev/null || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
lock_backup() {
  secure_dir
  mkdir "$BACKUPS/.lock" 2>/dev/null || error 'backup operation busy'
  OWN_BACKUP=1
}
new_scratch() {
  # Transient work belongs in TMPDIR, never the repository or home folder.
  _tmpbase=${TMPDIR:-/data/local/tmp}
  [ -d "$_tmpbase" ] && [ ! -L "$_tmpbase" ] || error 'unavailable TMPDIR'
  SCRATCH=$(mktemp -d "$_tmpbase/bindhosts-ux06.XXXXXXXX") || error 'cannot create scratch'
  chmod 0700 "$SCRATCH"
}
manifest() {
  (cd "$1" && sha256sum $FILES > SHA256SUMS) || error 'cannot create integrity manifest'
}
verify_manifest() {
  _snap=$1
  [ -d "$_snap" ] && [ ! -L "$_snap" ] || error 'snapshot missing or symlinked'
  [ -f "$_snap/SHA256SUMS" ] && [ ! -L "$_snap/SHA256SUMS" ] || error 'manifest missing'
  [ "$(wc -l < "$_snap/SHA256SUMS")" -eq 5 ] || error 'manifest entry count invalid'
  # Exact ordered filenames, no arbitrary sha256sum -c filenames.
  awk '
    BEGIN { f[1]="sources.txt";f[2]="sources_whitelist.txt";f[3]="blacklist.txt";f[4]="whitelist.txt";f[5]="custom.txt" }
    {if (length($1)!=64 || $1~/[^0-9a-f]/ || $2!=f[NR] || NF!=2) exit 8}
    END {if(NR!=5)exit 8}
  ' "$_snap/SHA256SUMS" || error 'manifest has unexpected names or hashes'
  for _file in $FILES; do
    [ -f "$_snap/$_file" ] && [ ! -L "$_snap/$_file" ] || error 'missing/nonregular backup member'
    [ "$(wc -c < "$_snap/$_file")" -le 2097152 ] || error 'backup file exceeds 2 MiB'
  done
  (cd "$_snap" && sha256sum -c SHA256SUMS >/dev/null) || error 'backup checksum mismatch'
}
verify_content() {
  _id=$1
  for _file in $FILES; do
    _kind=${_file%.txt}
    BH_CONFIG_ROOT="$ROOT" sh "$MODDIR/hosts_config_safe.sh" validate-snapshot "$_kind" "$_id" >/dev/null || error "invalid $_file content; no restore performed"
  done
}
log_receipt() {
  [ -f "$MODDIR/ux05_diagnostics.sh" ] || return 0
  # UX05 schema is deliberately fixed. Only record codes it supports.
  case "$1" in create|restore|import|export) : ;; *) return 0 ;; esac
  BH_DIAG_STATE="$ROOT" sh "$MODDIR/ux05_diagnostics.sh" record config "$1" ok CONFIG_BACKUP_OK >/dev/null 2>&1 || :
}
make_id() {
  _date=$(date -u +%Y%m%dT%H%M%S)
  _path=$(mktemp -d "$BACKUPS/bh-$_date-XXXXXX") || error 'cannot allocate snapshot'
  ID=${_path##*/}
  valid_id "$ID"
  chmod 0700 "$_path"
}
create() {
  lock_backup
  [ ! -e "$PENDING" ] && [ ! -L "$PENDING" ] || error 'unfinished restore; run recover before snapshotting'
  lock_config
  make_id
  for _file in $FILES; do ensure_source "$_file"; cp -p "$ROOT/$_file" "$BACKUPS/$ID/$_file" || error 'snapshot copy failed'; done
  manifest "$BACKUPS/$ID"
  verify_manifest "$BACKUPS/$ID"
  echo "BH_BACKUP_CREATED: $ID"
  log_receipt create
}
list_snapshots() {
  [ -d "$BACKUPS" ] && [ ! -L "$BACKUPS" ] || { echo 'BH_BACKUP_LIST_EMPTY'; return 0; }
  for _dir in "$BACKUPS"/bh-*; do
    [ -d "$_dir" ] && [ ! -L "$_dir" ] || continue
    _id=${_dir##*/}
    case "$_id" in bh-????????T??????-??????) : ;; *) continue ;; esac
    _bytes=0
    for _file in $FILES; do
      [ -f "$_dir/$_file" ] && [ ! -L "$_dir/$_file" ] || continue
      _n=$(wc -c < "$_dir/$_file")
      _bytes=$((_bytes+_n))
    done
    printf '%s|%s\n' "$_id" "$_bytes"
  done
}
verify() {
  [ "$#" -eq 1 ] || error 'verify SNAPSHOT_ID'
  valid_id "$1"
  verify_manifest "$BACKUPS/$1"
  verify_content "$1"
  echo "BH_BACKUP_VERIFY_PASS: $1"
}
preview() {
  [ "$#" -eq 1 ] || error 'preview SNAPSHOT_ID'
  valid_id "$1"
  verify_manifest "$BACKUPS/$1"
  verify_content "$1"
  for _file in $FILES; do
    ensure_source "$_file"
    _before=$(wc -c < "$ROOT/$_file")
    _after=$(wc -c < "$BACKUPS/$1/$_file")
    if cmp -s "$ROOT/$_file" "$BACKUPS/$1/$_file"; then _changed=no; else _changed=yes; fi
    printf 'BH_BACKUP_PREVIEW|%s|current_bytes=%s|backup_bytes=%s|changed=%s\n' "$_file" "$_before" "$_after" "$_changed"
  done
}
apply_originals() {
  # Called during rollback/boot recovery. Never delete PENDING if any byte differs.
  verify_manifest "$PENDING"
  for _file in $FILES; do
    ensure_source "$_file"
    _out=$(mktemp "$ROOT/.ux06-write.XXXXXXXX") || return 1
    if ! cp -p "$PENDING/$_file" "$_out" || ! mv -f "$_out" "$ROOT/$_file"; then
      rm -f "$_out"; return 1
    fi
  done
  for _file in $FILES; do cmp -s "$ROOT/$_file" "$PENDING/$_file" || return 1; done
  rm -rf "$PENDING" || return 1
  return 0
}
recover() {
  [ -e "$PENDING" ] || { echo 'BH_BACKUP_RECOVERY_CLEAN'; return 0; }
  [ -d "$PENDING" ] && [ ! -L "$PENDING" ] || error 'unsafe recovery snapshot'
  lock_backup
  lock_config
  if apply_originals; then echo 'BH_BACKUP_RECOVERY_PASS'; else error 'recovery failed; originals preserved in journal'; fi
}
restore() {
  [ "$#" -eq 1 ] || error 'restore SNAPSHOT_ID'
  valid_id "$1"
  lock_backup
  [ ! -e "$PENDING" ] && [ ! -L "$PENDING" ] || error 'pending restore exists; recover first'
  verify_manifest "$BACKUPS/$1"
  verify_content "$1"
  lock_config
  _prepared=$(mktemp -d "$ROOT/.ux06-restore-prepared.XXXXXXXX") || error 'cannot stage rollback journal'
  chmod 0700 "$_prepared"
  for _file in $FILES; do
    ensure_source "$_file"
    if ! cp -p "$ROOT/$_file" "$_prepared/$_file"; then
      rm -rf "$_prepared"; error 'cannot snapshot previous config'
    fi
  done
  manifest "$_prepared"
  verify_manifest "$_prepared"
  mv "$_prepared" "$PENDING" || error 'cannot publish persistent rollback journal'
  _i=0
  for _file in $FILES; do
    _out=$(mktemp "$ROOT/.ux06-write.XXXXXXXX") || error 'cannot stage config replacement'
    if ! cp "$BACKUPS/$1/$_file" "$_out" || ! chmod 0644 "$_out" || ! mv -f "$_out" "$ROOT/$_file"; then
      rm -f "$_out"
      apply_originals || error 'rollback failed; journal preserved'
      error 'restore failed; originals recovered'
    fi
    _i=$((_i+1))
    if [ "${BH_BACKUP_TEST_MODE:-0}" = 1 ] && [ "${BH_BACKUP_TEST_FAIL_AFTER:-0}" = "$_i" ]; then
      apply_originals || error 'injected failure and rollback failed; journal preserved'
      error 'injected failure: originals recovered'
    fi
  done
  for _file in $FILES; do
    if ! cmp -s "$ROOT/$_file" "$BACKUPS/$1/$_file"; then
      apply_originals || error 'postwrite verification and rollback failed; journal preserved'
      error 'postwrite mismatch; originals recovered'
    fi
  done
  rm -rf "$PENDING" || error 'restore succeeded but rollback journal cleanup failed'
  echo "BH_BACKUP_RESTORE_PASS: $1"
  log_receipt restore
}
choose_tar() {
  if command -v busybox >/dev/null 2>&1 && busybox tar --help >/dev/null 2>&1; then TAR='busybox tar'
  elif command -v tar >/dev/null 2>&1; then TAR='tar'
  else error 'tar unavailable'; fi
}
archive_list_ok() {
  _archive=$1
  $TAR -tf "$_archive" > "$SCRATCH/list" || error 'invalid archive listing'
  [ "$(wc -l < "$SCRATCH/list")" -eq 6 ] || error 'unexpected archive members'
  awk 'BEGIN{f[1]="sources.txt";f[2]="sources_whitelist.txt";f[3]="blacklist.txt";f[4]="whitelist.txt";f[5]="custom.txt";f[6]="SHA256SUMS"} {if($0!=f[NR])exit 8} END{if(NR!=6)exit 8}' "$SCRATCH/list" || error 'unexpected archive names/order'
  $TAR -tvf "$_archive" > "$SCRATCH/types" || error 'invalid archive metadata'
  [ "$(wc -l < "$SCRATCH/types")" -eq 6 ] || error 'unexpected archive metadata count'
  # Regular files only. Reject archive symlinks, devices, directories and hardlinks BEFORE extraction.
  LC_ALL=C awk 'substr($0,1,1)!="-" {exit 8}' "$SCRATCH/types" || error 'archive contains nonregular members'
}
export_snapshot() {
  [ "$#" -eq 1 ] || error 'export SNAPSHOT_ID'
  valid_id "$1"
  verify_manifest "$BACKUPS/$1"
  [ -d "$DOWNLOAD" ] && [ ! -L "$DOWNLOAD" ] || error 'shared Downloads inaccessible'
  choose_tar
  new_scratch
  _archive="$SCRATCH/bindhosts-backup-$1.tar"
  (cd "$BACKUPS/$1" && $TAR -cf "$_archive" $FILES SHA256SUMS) || error 'cannot create archive'
  archive_list_ok "$_archive"
  _destination="$DOWNLOAD/bindhosts-backup-$1.tar"
  [ ! -e "$_destination" ] && [ ! -L "$_destination" ] || error 'export destination already exists'
  cp "$_archive" "$_destination" || error 'cannot write Downloads'
  chmod 0600 "$_destination" 2>/dev/null || :
  echo "BH_BACKUP_EXPORTED: $_destination"
  log_receipt export
}
imports_list() {
  [ -d "$DOWNLOAD" ] && [ ! -L "$DOWNLOAD" ] || { echo BH_BACKUP_IMPORTS_EMPTY; return 0; }
  for _path in "$DOWNLOAD"/bindhosts-backup-bh-*.tar; do
    [ -f "$_path" ] && [ ! -L "$_path" ] || continue
    _name=${_path##*/}
    case "$_name" in bindhosts-backup-bh-????????T??????-??????.tar) : ;; *) continue ;; esac
    case "$_name" in *[!A-Za-z0-9_.-]*|*..*) continue ;; esac
    echo "$_name"
  done
}
import_archive() {
  [ "$#" -eq 1 ] || error 'import DOWNLOADS_BASENAME'
  case "$1" in bindhosts-backup-bh-????????T??????-??????.tar) : ;; *) error 'unsupported archive name' ;; esac
  case "$1" in *[!A-Za-z0-9_.-]*|*..*|*/*) error 'invalid archive name' ;; esac
  [ -d "$DOWNLOAD" ] && [ ! -L "$DOWNLOAD" ] || error 'Downloads unavailable'
  [ -f "$DOWNLOAD/$1" ] && [ ! -L "$DOWNLOAD/$1" ] || error 'archive missing/symlinked'
  [ "$(wc -c < "$DOWNLOAD/$1")" -le 12000000 ] || error 'archive exceeds 12 MB'
  lock_backup
  new_scratch
  cp "$DOWNLOAD/$1" "$SCRATCH/input.tar" || error 'cannot stage import'
  choose_tar
  archive_list_ok "$SCRATCH/input.tar"
  make_id
  _snap="$BACKUPS/$ID"
  if ! (cd "$_snap" && $TAR -xf "$SCRATCH/input.tar"); then rm -rf "$_snap"; error 'archive extraction failed'; fi
  if ! (verify_manifest "$_snap" && verify_content "$ID"); then
    rm -rf "$_snap"
    error 'import archive failed integrity/content validation'
  fi
  echo "BH_BACKUP_IMPORTED: $ID"
  log_receipt import
}
health() {
  # Report aggregate counts only, never domains or source URLs.
  for _f in sources.txt sources_whitelist.txt blacklist.txt whitelist.txt; do
    ensure_source "$_f"
    awk -v kind="$_f" '
      {line=$0;sub(/\r$/,"",line);if(line=="" || substr(line,1,1)=="#")next;
       if(index(line,"disabled|")==1){disabled++;next};sub(/[[:space:]]+#.*/, "",line);
       if(seen[line]++){duplicates++}else{enabled++}}
      END{printf "BH_BACKUP_HEALTH|%s|enabled=%d|disabled=%d|duplicates=%d\n",kind,enabled,disabled,duplicates}
    ' "$ROOT/$_f" || error 'cannot scan source health'
  done
}
CMD=${1:-status}
[ "$#" -eq 0 ] || shift
case "$CMD" in
  status)
    [ "$#" -eq 0 ] || error 'status takes no arguments'
    if [ -e "$PENDING" ]; then echo 'restore_journal=pending'; else echo 'restore_journal=clean'; fi
    echo 'backup_schema=1'
    ;;
  health) [ "$#" -eq 0 ] || error 'health takes no arguments'; health ;;
  list) [ "$#" -eq 0 ] || error 'list takes no arguments'; list_snapshots ;;
  create) [ "$#" -eq 0 ] || error 'create takes no arguments'; create ;;
  verify) verify "$@" ;;
  preview) preview "$@" ;;
  restore) restore "$@" ;;
  recover) [ "$#" -eq 0 ] || error 'recover takes no arguments'; recover ;;
  export) export_snapshot "$@" ;;
  import) import_archive "$@" ;;
  imports) [ "$#" -eq 0 ] || error 'imports takes no arguments'; imports_list ;;
  *) error 'usage: status|health|list|create|verify ID|preview ID|restore ID|recover|export ID|imports|import NAME' ;;
esac
