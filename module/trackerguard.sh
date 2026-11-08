#!/system/bin/sh
# TrackerGuard R0 for bindhosts. Network blocking stays with upstream bindhosts.
# This script manages ONLY its own IFW XML and explicitly requested components.
# No APK parsing or automatic tracker discovery in R0.
set -u

TG_STATE_DIR=${TG_STATE_DIR:-/data/adb/bindhosts/trackerguard}
TG_IFW_DIR=${TG_IFW_DIR:-/data/system/ifw}
TG_FILE=$TG_IFW_DIR/bindhosts_trackerguard.xml
TG_RULES=$TG_STATE_DIR/rules.tsv
TG_MARKER='<!-- bindhosts-tracker: managed IFW file -->'
TG_PM=${TG_PM:-pm}
TG_ROOT_SKIP=${TG_ROOT_SKIP:-0}  # For isolated tests only; never set on a device.

say() { printf '%s\n' "$*"; }
die() { say "TrackerGuard: $*" >&2; exit 1; }
usage() {
  cat <<'HELP'
bindhosts tracker — optional app-component firewall
Usage:
  bindhosts tracker status
  bindhosts tracker list
  bindhosts tracker scan PKG
  bindhosts tracker preview PKG
  bindhosts tracker block PKG
  bindhosts tracker add PKG service|receiver|activity CLASS
  bindhosts tracker remove PKG service|receiver|activity CLASS
  bindhosts tracker restore PKG
  bindhosts tracker restore --all
  bindhosts tracker apply
  bindhosts tracker help

CLASS may be a full Java class name, .RelativeClass, or PKG/CLASS.
Only installed user apps are accepted by default; system apps are refused.
Blocks are explicit; R0 does not automatically discover trackers.
Network blocking remains handled by existing bindhosts commands/WebUI.
HELP
}
check_root() {
  [ "$TG_ROOT_SKIP" = 1 ] && return 0
  [ "$(id -u)" = 0 ] || die 'root required (run: su -c "bindhosts tracker ...")'
}
validate_package() {
  case "$1" in ''|.*|*..*|*[!a-zA-Z0-9_.]*) die "invalid package: $1" ;; esac
  case "$1" in *.*) : ;; *) die "invalid package: $1" ;; esac
}
validate_type() {
  case "$1" in service|receiver|activity) : ;; *) die "invalid component type: $1" ;; esac
}
normalize_class() {
  _pkg=$1 _cls=$2
  case "$_cls" in
    "$_pkg"/*) _cls=${_cls#*/} ;;
    */*) die "component must belong to $_pkg" ;;
  esac
  case "$_cls" in
    .*) _cls=$_pkg$_cls ;;
  esac
  case "$_cls" in ''|.*|*..*|*[!a-zA-Z0-9_.$]*) die "invalid component class: $_cls" ;; esac
  case "$_cls" in *.*) : ;; *) die "use the fully-qualified component class" ;; esac
  printf '%s\n' "$_cls"
}
check_user_package() {
  _p=$1
  "$TG_PM" list packages -3 2>/dev/null | grep -Fxq "package:$_p" || die "not an installed user app: $_p"
}
prepare() {
  [ -d "$TG_IFW_DIR" ] || die "IFW directory missing: $TG_IFW_DIR"
  mkdir -p "$TG_STATE_DIR" || die 'cannot create state directory'
  chmod 700 "$TG_STATE_DIR" || die 'cannot secure state directory'
  [ -f "$TG_RULES" ] || : > "$TG_RULES"
  chmod 600 "$TG_RULES"
}
check_owned() {
  if [ -e "$TG_FILE" ] && ! grep -Fq "$TG_MARKER" "$TG_FILE"; then
    die "refusing to replace foreign IFW file: $TG_FILE"
  fi
  [ ! -L "$TG_FILE" ] || die 'refusing symbolic-link IFW file'
}
lock() {
  mkdir "$TG_STATE_DIR/.lock" 2>/dev/null || die 'another TrackerGuard operation is running (or a stale lock exists)'
  trap 'rmdir "$TG_STATE_DIR/.lock" 2>/dev/null || true' EXIT HUP INT TERM
}
# Generate IFW file with only exact components. All values already syntax-validated.
# Never touch, read, merge, or delete App Manager's own IFW files.
write_ifw() {
  check_owned
  _input=$1
  _tmp="$TG_IFW_DIR/.bindhosts_trackerguard.$$.tmp"
  (
    printf '%s\n' "$TG_MARKER" '<rules>'
    while IFS='|' read -r _pkg _type _cls; do
      [ -n "$_pkg" ] || continue
      _name="$_pkg/$_cls"
      case "$_type" in
        receiver) _tag=broadcast ;;
        service|activity) _tag=$_type ;;
        *) exit 11 ;;
      esac
      printf '  <%s block="true" log="false"><component-filter name="%s"/></%s>\n' "$_tag" "$_name" "$_tag"
    done < "$_input"
    printf '%s\n' '</rules>'
  ) > "$_tmp" || { rm -f "$_tmp"; die 'failed to render IFW XML'; }
  chmod 600 "$_tmp" || { rm -f "$_tmp"; die 'chmod on IFW failed'; }
  chown 1000:1000 "$_tmp" 2>/dev/null || true
  if command -v restorecon >/dev/null 2>&1; then restorecon "$_tmp" >/dev/null 2>&1 || true; fi
  mv -f "$_tmp" "$TG_FILE" || { rm -f "$_tmp"; die 'atomic IFW replacement failed'; }
  if command -v restorecon >/dev/null 2>&1; then restorecon "$TG_FILE" >/dev/null 2>&1 || true; fi
}
write_rules() {
  _candidate=$1
  # First install the candidate firewall, then commit the new rule database.
  # Reapplying can repair a rare interrupted state-commit.
  write_ifw "$_candidate"
  mv -f "$_candidate" "$TG_RULES" || die 'failed to commit state; rerun apply after restoring rule database'
  chmod 600 "$TG_RULES"
}
status() {
  say "State: $TG_STATE_DIR"
  say "IFW file: $TG_FILE"
  if [ -e "$TG_FILE" ]; then
    if grep -Fq "$TG_MARKER" "$TG_FILE"; then say 'IFW ownership: TrackerGuard'; else say 'IFW ownership: FOREIGN (not modified)'; fi
  else say 'IFW ownership: no file'; fi
  if [ -f "$TG_RULES" ]; then say "Explicit blocks: $(grep -c '|' "$TG_RULES" || true)"; else say 'Explicit blocks: 0'; fi
  say 'R1 inventory: available (base APK only); automatic install watcher: not enabled'
}
list_rules() {
  [ -f "$TG_RULES" ] || { say 'No blocks'; return 0; }
  [ -s "$TG_RULES" ] || { say 'No blocks'; return 0; }
  cat "$TG_RULES"
}
add_rule() {
  [ "$#" = 3 ] || die 'usage: add PKG type CLASS'
  validate_package "$1"; validate_type "$2"
  _p=$1 _t=$2
  _c=$(normalize_class "$_p" "$3") || exit 1
  check_user_package "$_p"
  _entry="$_p|$_t|$_c"
  prepare; lock; check_owned
  if grep -Fxq "$_entry" "$TG_RULES"; then say 'Rule already exists'; exit 0; fi
  _pending="$TG_STATE_DIR/rules.$$.pending"
  cat "$TG_RULES" > "$_pending"
  printf '%s\n' "$_entry" >> "$_pending"
  LC_ALL=C sort -u "$_pending" -o "$_pending" || die 'sort failed'
  write_rules "$_pending"
  say "IFW rule written (device enforcement unverified): $_entry"
}
remove_rule() {
  [ "$#" = 3 ] || die 'usage: remove PKG type CLASS'
  validate_package "$1"; validate_type "$2"
  _p=$1 _t=$2
  _c=$(normalize_class "$_p" "$3") || exit 1
  _entry="$_p|$_t|$_c"
  prepare; lock; check_owned
  _pending="$TG_STATE_DIR/rules.$$.pending"
  grep -Fvx "$_entry" "$TG_RULES" > "$_pending" || :
  write_rules "$_pending"
  say "Removed rule: $_entry"
}
restore_pkg() {
  [ "$#" = 1 ] || die 'usage: restore PKG | --all'
  prepare; lock; check_owned
  if [ "$1" = '--all' ]; then
    # Only delete our owned file, not another manager's XML rules.
    if [ -e "$TG_FILE" ]; then rm -f "$TG_FILE" || die 'could not remove owned IFW file'; fi
    : > "$TG_RULES"
    say 'Removed all TrackerGuard-owned rules'
    return 0
  fi
  validate_package "$1"
  _pending="$TG_STATE_DIR/rules.$$.pending"
  awk -F'|' -v pkg="$1" '$1 != pkg' "$TG_RULES" > "$_pending" || die 'rule filtering failed'
  write_rules "$_pending"
  say "Restored TrackerGuard rules for $1"
}
apply_rules() {
  prepare; lock; check_owned
  # Validate the persistent database before an install/update reconciliation.
  while IFS='|' read -r _p _t _c; do
    [ -n "$_p" ] || continue
    validate_package "$_p"; validate_type "$_t"
    _normalized=$(normalize_class "$_p" "$_c") || die 'invalid rule class'
    [ "$_c" = "$_normalized" ] || die 'noncanonical persistent rule; refusing'
    # Drop rules only when explicitly removed. Uninstalled apps cannot launch them.
  done < "$TG_RULES"
  write_ifw "$TG_RULES"
  say 'Reapplied TrackerGuard-owned IFW rules'
}

TG_R1_MODDIR=${TG_R1_MODDIR:-/data/adb/modules/bindhosts}
. "$TG_R1_MODDIR/trackerguard_r1.sh"

check_root
_cmd=${1:-help}; [ "$#" -eq 0 ] || shift
case "$_cmd" in
  help|-h|--help) usage ;;
  status) status ;;
  list) list_rules ;;
  scan) tg_r1_scan "$@" ;;
  preview) tg_r1_preview "$@" ;;
  block) tg_r1_block "$@" ;;
  add) add_rule "$@" ;;
  remove) remove_rule "$@" ;;
  restore) restore_pkg "$@" ;;
  apply) apply_rules ;;
  *) usage; die "unknown command: $_cmd" ;;
esac
