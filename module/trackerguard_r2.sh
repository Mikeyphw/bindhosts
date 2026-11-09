#!/system/bin/sh
# SPDX-License-Identifier: MIT
# R2: explicit, narrow, reversible auto-management of known broadcast receiver trackers.
# Sourced by trackerguard.sh. R0 remains the source of truth for the IFW XML writer.
TG_R2_ENROLLED=$TG_STATE_DIR/enrolled.tsv
TG_R2_EXCLUDED=$TG_STATE_DIR/excluded.tsv
TG_R2_AUTO=$TG_STATE_DIR/auto.tsv
TG_R2_SEEN=$TG_STATE_DIR/seen.tsv
TG_R2_ENABLED=$TG_STATE_DIR/monitor.enabled
TG_R2_PID=$TG_STATE_DIR/watch.pid
TG_R2_LOG=$TG_STATE_DIR/monitor.log
TG_R2_INTERVAL=120
# State and diagnostics are private to root; never expose package inventory to apps.
umask 077

# Must be called under root; no symlink follows in persistent tracking metadata.
tg_r2_init() {
  prepare
  for _tg_file in "$TG_R2_ENROLLED" "$TG_R2_EXCLUDED" "$TG_R2_AUTO" "$TG_R2_SEEN"; do
    [ ! -L "$_tg_file" ] || die "refusing symlink state: $_tg_file"
    [ -f "$_tg_file" ] || : > "$_tg_file" || die "cannot initialize: $_tg_file"
    chmod 600 "$_tg_file" || die "cannot secure: $_tg_file"
  done
}

tg_r2_in() { grep -Fxq "$2" "$1"; }

tg_r2_set_add() {
  _tg_dest=$1; _tg_item=$2
  if ! tg_r2_in "$_tg_dest" "$_tg_item"; then
    printf '%s\n' "$_tg_item" >> "$_tg_dest" || die "cannot update $_tg_dest"
    LC_ALL=C sort -u "$_tg_dest" -o "$_tg_dest" || die "cannot normalize $_tg_dest"
  fi
}

tg_r2_set_drop() {
  _tg_dest=$1; _tg_item=$2
  _tg_tmp=$(mktemp "$TG_STATE_DIR/r2-set.XXXXXXXX") || die 'cannot stage set'
  grep -Fvx "$_tg_item" "$_tg_dest" > "$_tg_tmp" || :
  chmod 600 "$_tg_tmp"
  mv -f "$_tg_tmp" "$_tg_dest" || die "cannot replace $_tg_dest"
}

tg_r2_prune_auto_entry() {
  [ -f "$TG_R2_AUTO" ] || return 0
  tg_r2_set_drop "$TG_R2_AUTO" "$1"
}

tg_r2_is_enrolled() { tg_r2_in "$TG_R2_ENROLLED" "$1"; }
tg_r2_is_excluded() { tg_r2_in "$TG_R2_EXCLUDED" "$1"; }

# With lock already held. Never remove manual R0 rules, even if they also match a signature.
# Second arg 'prune' is used for unenroll, exclusion, and confirmed uninstallation.
tg_r2_reconcile_locked() {
  [ "$#" -ge 1 ] || die 'usage: reconcile PACKAGE'
  _tg_pkg=$1; _tg_mode=${2:-normal}
  validate_package "$_tg_pkg"
  _tg_dir=$(mktemp -d "$TG_STATE_DIR/r2-reconcile.XXXXXXXX") || die 'cannot stage reconciliation'
  _tg_desired=$_tg_dir/desired
  _tg_rules=$_tg_dir/rules
  _tg_autos=$_tg_dir/auto
  : > "$_tg_desired"

  if [ "$_tg_mode" != prune ] && tg_r2_is_enrolled "$_tg_pkg" && ! tg_r2_is_excluded "$_tg_pkg"; then
    if ! check_user_package "$_tg_pkg" >/dev/null 2>&1; then
      # A removed user APK cannot execute old receiver/service components.
      _tg_mode=prune
    else
      if ! tg_r1_matches "$_tg_pkg" > "$_tg_dir/matches"; then
        rm -rf "$_tg_dir"
        say "TrackerGuard R2: scan failed for $_tg_pkg; retaining previous rules" >&2
        return 1
      fi
      # Only receivers are validated on rooted Android 16. No auto services/activities/providers.
      awk -F'|' -v pkg="$_tg_pkg" '
        $1=="receiver" && $4=="true" && $5=="review" {
          print pkg "|" $1 "|" $2
        }' "$_tg_dir/matches" | LC_ALL=C sort -u > "$_tg_desired"
    fi
  fi

  # Start with all rules except *our own* previous auto rules for this package.
  awk -F'|' -v pkg="$_tg_pkg" '
    FILENAME==ARGV[1] { if ($1==pkg) automatic[$0]=1; next }
    !(($1==pkg) && ($0 in automatic)) { if ($0!="") print }
  ' "$TG_R2_AUTO" "$TG_RULES" > "$_tg_rules" || die 'cannot stage rules'
  awk -F'|' -v pkg="$_tg_pkg" '$1!=pkg && $0!="" {print}' "$TG_R2_AUTO" > "$_tg_autos"

  while IFS= read -r _tg_entry; do
    [ -n "$_tg_entry" ] || continue
    if tg_r2_in "$TG_R2_AUTO" "$_tg_entry" || ! tg_r2_in "$TG_RULES" "$_tg_entry"; then
      printf '%s\n' "$_tg_entry" >> "$_tg_rules"
      printf '%s\n' "$_tg_entry" >> "$_tg_autos"
    fi
    # If it pre-existed as an explicit R0 rule, leave it manual.
  done < "$_tg_desired"
  LC_ALL=C sort -u "$_tg_rules" -o "$_tg_rules" || die 'cannot sort rules'
  LC_ALL=C sort -u "$_tg_autos" -o "$_tg_autos" || die 'cannot sort automatic ownership'
  chmod 600 "$_tg_rules" "$_tg_autos"

  if ! cmp -s "$_tg_rules" "$TG_RULES"; then
    # Existing R0 writer atomically replaces *only* the bindhosts-owned IFW file.
    write_rules "$_tg_rules"
  fi
  # The ownership record commits only after the IFW+rules transaction succeeds.
  mv -f "$_tg_autos" "$TG_R2_AUTO" || die 'cannot commit auto ownership'
  chmod 600 "$TG_R2_AUTO"
  rm -rf "$_tg_dir"
  say "R2_RECONCILE_PASS: $_tg_pkg ($_tg_mode)"
}

tg_r2_reconcile() {
  [ "$#" = 1 ] || die 'usage: reconcile PACKAGE'
  tg_r2_init; lock; check_owned
  tg_r2_reconcile_locked "$1"
}

tg_r2_enroll() {
  [ "$#" = 1 ] || die 'usage: enroll PACKAGE'
  validate_package "$1"
  check_user_package "$1"
  tg_r2_init; lock; check_owned
  tg_r2_set_add "$TG_R2_ENROLLED" "$1"
  if tg_r2_is_excluded "$1"; then
    say "R2_ENROLLED_EXCLUDED: $1 (no blocks)"
  else
    tg_r2_reconcile_locked "$1"
  fi
}

tg_r2_unenroll() {
  [ "$#" = 1 ] || die 'usage: unenroll PACKAGE'
  validate_package "$1"
  tg_r2_init; lock; check_owned
  tg_r2_reconcile_locked "$1" prune || return 1
  tg_r2_set_drop "$TG_R2_ENROLLED" "$1"
  say "R2_UNENROLL_PASS: $1 (manual rules preserved)"
}

tg_r2_exclude() {
  [ "$#" = 1 ] || die 'usage: exclude PACKAGE'
  validate_package "$1"
  tg_r2_init; lock; check_owned
  tg_r2_reconcile_locked "$1" prune || return 1
  tg_r2_set_add "$TG_R2_EXCLUDED" "$1"
  say "R2_EXCLUDE_PASS: $1 (manual rules preserved)"
}

tg_r2_include() {
  [ "$#" = 1 ] || die 'usage: include PACKAGE'
  validate_package "$1"
  tg_r2_init; lock; check_owned
  tg_r2_set_drop "$TG_R2_EXCLUDED" "$1"
  if tg_r2_is_enrolled "$1"; then tg_r2_reconcile_locked "$1"; fi
  say "R2_INCLUDE_PASS: $1"
}

# Preserve manual intent: adding an already auto-blocked component promotes its ownership.
tg_r2_manual_add() {
  [ "$#" = 3 ] || { add_rule "$@"; return; }
  validate_package "$1"; validate_type "$2"
  _tg_manual_cls=$(normalize_class "$1" "$3") || return 1
  _tg_manual_entry="$1|$2|$_tg_manual_cls"
  if [ -f "$TG_R2_AUTO" ] && tg_r2_in "$TG_R2_AUTO" "$_tg_manual_entry"; then
    check_user_package "$1"
    tg_r2_init; lock; check_owned
    tg_r2_prune_auto_entry "$_tg_manual_entry"
    say "R2_PROMOTED_TO_MANUAL: $_tg_manual_entry"
    return 0
  fi
  add_rule "$@"
}

# Explicit R1 'block PACKAGE' promotes any previously automatic rules
# for that app, preserving the user's new manual blocking intent on unenroll.
tg_r2_manual_block() {
  [ "$#" = 1 ] || { tg_r1_block "$@"; return; }
  tg_r2_init
  tg_r1_block "$@" || return 1
  if [ -s "$TG_R2_AUTO" ]; then
    _tg_promoted=$(mktemp "$TG_STATE_DIR/r2-promote.XXXXXXXX") || die 'cannot stage promotion'
    awk -F'|' -v pkg="$1" '$1!=pkg {print}' "$TG_R2_AUTO" > "$_tg_promoted"
    chmod 600 "$_tg_promoted"
    mv -f "$_tg_promoted" "$TG_R2_AUTO" || die 'cannot persist manual promotion'
  fi
  say "R2_MANUAL_BATCH_BLOCK: $1"
}

tg_r2_manual_remove() {
  tg_r2_init
  remove_rule "$@"
  [ "$#" = 3 ] || return 0
  _tg_cls=$(normalize_class "$1" "$3") || return 1
  tg_r2_prune_auto_entry "$1|$2|$_tg_cls"
}

tg_r2_manual_restore() {
  [ "$#" = 1 ] || { restore_pkg "$@"; return; }
  tg_r2_init
  restore_pkg "$@"
  if [ "$1" = --all ]; then
    : > "$TG_R2_AUTO"
    : > "$TG_R2_ENROLLED"
  else
    _tg_pkg=$1
    _tg_tmp=$(mktemp "$TG_STATE_DIR/r2-restore.XXXXXXXX") || die 'cannot stage restore'
    awk -F'|' -v pkg="$_tg_pkg" '$1!=pkg' "$TG_R2_AUTO" > "$_tg_tmp"
    chmod 600 "$_tg_tmp"
    mv -f "$_tg_tmp" "$TG_R2_AUTO"
    tg_r2_set_drop "$TG_R2_ENROLLED" "$_tg_pkg"
  fi
}

# Parse one efficient PackageManager snapshot (versionCode and source APK path).
# On Android 16 these flags are supported; an error must not replace the last snapshot.
tg_r2_snapshot() {
  _tg_out=$1
  _tg_raw=$(mktemp "$TG_STATE_DIR/r2-pm.XXXXXXXX") || {
    say 'R2_SNAPSHOT_FAILED: private staging unavailable' >&2
    return 1
  }
  # The original error collapsed pm failures, invalid records and sort failures
  # into one message. Keep those cases fail-closed, but make them diagnosable.
  if ! "$TG_PM" list packages -3 -f --show-versioncode > "$_tg_raw"; then
    # Some OEM / KernelSU environments expose cmd package but not a working pm
    # wrapper in the root process. Both query the platform PackageManager.
    if command -v cmd >/dev/null 2>&1; then
      if ! cmd package list packages -3 -f --show-versioncode > "$_tg_raw"; then
        rm -f "$_tg_raw"
        say 'R2_SNAPSHOT_FAILED: both pm and cmd package queries failed' >&2
        return 1
      fi
      say 'R2_SNAPSHOT_PM_FALLBACK: using cmd package' >&2
    else
      rm -f "$_tg_raw"
      say 'R2_SNAPSHOT_FAILED: pm query failed; cmd package unavailable' >&2
      return 1
    fi
  fi
  # Android version and package paths can contain base64 = signs. Select the
  # LAST '=' before versionCode, never blindly split the APK path on '='.
  # Ignore blank lines only; refuse unrecognized text or invalid package rows.
  # Do not expose installed package identifiers in diagnostic output.
  if ! awk '
    /^[[:space:]]*$/ {next}
    {
      row=$0; sub(/\r$/, "", row)
      if (substr(row,1,8)!="package:") {bad++; next}
      if (!match(row,/ versionCode:[0-9]+($|[[:space:]])/)) {bad++; next}
      before=substr(row,1,RSTART-1)
      version=substr(row,RSTART+13,RLENGTH-13)
      sub(/[[:space:]].*$/, "", version)
      if (version !~ /^[0-9]+$/ || before !~ /^package:.*\.apk=[A-Za-z0-9_.]+$/) {bad++;next}
      name=before; sub(/^.*=/,"",name)
      if (seen[name]++) {bad++;next}
      if (name !~ /^[A-Za-z_][A-Za-z0-9_.]*$/ || index(name,".")==0 || index(name,"..")) {bad++;next}
      rest=" " substr(row,RSTART+RLENGTH)
      # Only allow known optional flags following the version. A failure
      # retains the previous observation snapshot and all IFW rules.
      if (rest !~ /^([[:space:]]+(stopped=(true|false)|uid:[0-9,]+|installer=[A-Za-z0-9_.]+))*[[:space:]]*$/) {bad++;next}
      print name "|" before " versionCode:" version
      count++
    }
    END {
      if (bad || !count) {
        printf "R2_SNAPSHOT_PARSE_FAILED: valid=%d invalid=%d (package names redacted)\n", count, bad > "/dev/stderr"
        exit 7
      }
    }
  ' "$_tg_raw" > "$_tg_out"; then
    rm -f "$_tg_raw" "$_tg_out"
    return 1
  fi
  rm -f "$_tg_raw"
  if ! LC_ALL=C sort -u "$_tg_out" -o "$_tg_out" || [ ! -s "$_tg_out" ]; then
    say 'R2_SNAPSHOT_FAILED: normalization or empty inventory' >&2
    return 1
  fi
  return 0
}

tg_r2_once() {
  [ "$#" -le 1 ] || die 'usage: monitor once'
  tg_r2_init; lock; check_owned
  _tg_dir=$(mktemp -d "$TG_STATE_DIR/r2-once.XXXXXXXX") || die 'cannot stage snapshot'
  if ! tg_r2_snapshot "$_tg_dir/current"; then
    rm -rf "$_tg_dir"; die 'package snapshot failed; state retained'
  fi
  cp "$_tg_dir/current" "$_tg_dir/next" || die 'cannot stage next snapshot'
  _tg_baseline=0
  [ -s "$TG_R2_SEEN" ] || _tg_baseline=1
  _tg_changes=0
  while IFS='|' read -r _tg_pkg _tg_fp; do
    [ -n "$_tg_pkg" ] || continue
    _tg_old=$(awk -F'|' -v pkg="$_tg_pkg" '$1==pkg { print substr($0,length($1)+2); exit }' "$TG_R2_SEEN")
    [ "$_tg_fp" = "$_tg_old" ] && continue
    if [ "$_tg_baseline" -eq 0 ]; then
      _tg_changes=$((_tg_changes+1))
      if [ -z "$_tg_old" ]; then _tg_event=installed; else _tg_event=updated; fi
      printf '%s|%s|%s\n' "$(date +%s)" "$_tg_event" "$_tg_pkg" >> "$TG_R2_LOG"
      say "R2_OBSERVED: $_tg_event $_tg_pkg"
    fi
    # Even after an empty snapshot (e.g. uninstall), an already enrolled
    # package must be reconciled on reinstall. Baseline is NOT auto-enrollment.
    if tg_r2_is_enrolled "$_tg_pkg" && ! tg_r2_is_excluded "$_tg_pkg"; then
      if ! (tg_r2_reconcile_locked "$_tg_pkg"); then
        # Retry the failed scan next cycle, but DO NOT mark the installed app
        # as absent: pruning uses 'current', not this next-cycle snapshot.
        awk -F'|' -v pkg="$_tg_pkg" '$1!=pkg' "$_tg_dir/next" > "$_tg_dir/filtered"
        mv -f "$_tg_dir/filtered" "$_tg_dir/next"
      fi
    fi
  done < "$_tg_dir/current"
  # Removed apps: drop only R2-owned rules (manual rules remain until explicit restore).
  while IFS= read -r _tg_pkg; do
    [ -n "$_tg_pkg" ] || continue
    if ! awk -F'|' -v pkg="$_tg_pkg" '$1==pkg {found=1; exit} END{exit !found}' "$_tg_dir/current"; then
      (tg_r2_reconcile_locked "$_tg_pkg" prune) || die "cannot prune removed app $_tg_pkg"
      [ "$_tg_baseline" -eq 1 ] || printf '%s|removed|%s\n' "$(date +%s)" "$_tg_pkg" >> "$TG_R2_LOG"
    fi
  done < "$TG_R2_ENROLLED"
  chmod 600 "$_tg_dir/next"
  mv -f "$_tg_dir/next" "$TG_R2_SEEN" || die 'cannot commit snapshot'
  rm -rf "$_tg_dir"
  if [ -f "$TG_R2_LOG" ] && [ ! -L "$TG_R2_LOG" ] && [ "$(wc -c < "$TG_R2_LOG")" -gt 524288 ]; then
    _tg_logtemp=$(mktemp "$TG_STATE_DIR/r2-log.XXXXXXXX") || die 'cannot stage log rotation'
    tail -n 1000 "$TG_R2_LOG" > "$_tg_logtemp"
    chmod 600 "$_tg_logtemp"
    mv -f "$_tg_logtemp" "$TG_R2_LOG"
  fi
  say "R2_MONITOR_ONCE_PASS: changes=$_tg_changes baseline=$_tg_baseline"
}

tg_r2_watch() {
  tg_r2_init
  [ -f "$TG_R2_ENABLED" ] || { say 'R2_MONITOR_DISABLED'; return 0; }
  [ ! -L "$TG_R2_PID" ] || die 'refusing symlink monitor pid'
  if [ -s "$TG_R2_PID" ]; then
    _tg_pid=$(cat "$TG_R2_PID")
    if [ "$_tg_pid" != "$$" ] && kill -0 "$_tg_pid" 2>/dev/null &&
       [ -r "/proc/$_tg_pid/cmdline" ] &&
       tr '\000' ' ' < "/proc/$_tg_pid/cmdline" | grep -Fq 'trackerguard'; then
      say 'R2_MONITOR_ALREADY_RUNNING'; return 0
    fi
  fi
  printf '%s\n' "$$" > "$TG_R2_PID"
  trap 'rm -f "$TG_R2_PID"' EXIT HUP INT TERM
  while [ -f "$TG_R2_ENABLED" ]; do
    sh "${TG_R2_MOD_SCRIPT:-$TG_R1_MODDIR/trackerguard.sh}" monitor once ||
      say 'R2_MONITOR_CYCLE_FAILED: keeping previous state'
    sleep "$TG_R2_INTERVAL"
  done
}

tg_r2_monitor() {
  _tg_cmd=${1:-status}; [ "$#" = 0 ] || shift
  case "$_tg_cmd" in
    enable)
      [ "$#" = 0 ] || die 'usage: monitor enable'
      tg_r2_init; [ ! -L "$TG_R2_ENABLED" ] || die 'invalid monitor flag'
      : > "$TG_R2_ENABLED"; chmod 600 "$TG_R2_ENABLED"
      if ! tg_r2_once; then
        rm -f "$TG_R2_ENABLED"
        die 'initial snapshot failed; monitoring remains disabled'
      fi
      if [ "${TG_R2_NO_WATCH_START:-0}" != 1 ]; then
        sh "${TG_R2_MOD_SCRIPT:-$TG_R1_MODDIR/trackerguard.sh}" monitor watch >> "$TG_R2_LOG" 2>&1 &
      fi
      say 'R2_MONITOR_ENABLED: observation mode, 120s polling' ;;
    disable)
      [ "$#" = 0 ] || die 'usage: monitor disable'
      tg_r2_init; rm -f "$TG_R2_ENABLED"
      if [ -s "$TG_R2_PID" ]; then
        _tg_pid=$(cat "$TG_R2_PID")
        case "$_tg_pid" in *[!0-9]*|'') : ;; *)
          if [ -r "/proc/$_tg_pid/cmdline" ] &&
             tr '\000' ' ' < "/proc/$_tg_pid/cmdline" | grep -Fq 'trackerguard'; then
            kill "$_tg_pid" 2>/dev/null || :
          fi ;;
        esac
      fi
      say 'R2_MONITOR_DISABLED: existing IFW blocks preserved' ;;
    once) [ "$#" = 0 ] || die 'usage: monitor once'; tg_r2_once ;;
    watch) [ "$#" = 0 ] || die 'usage: monitor watch'; tg_r2_watch ;;
    status)
      [ "$#" = 0 ] || die 'usage: monitor status'
      tg_r2_init
      if [ -f "$TG_R2_ENABLED" ]; then say 'Monitor: enabled (observational unless app enrolled)'; else say 'Monitor: disabled'; fi
      say "Interval: $TG_R2_INTERVAL seconds"
      say "Enrolled: $(wc -l < "$TG_R2_ENROLLED")"
      say "Excluded: $(wc -l < "$TG_R2_EXCLUDED")"
      say "R2 automatic rules: $(wc -l < "$TG_R2_AUTO")" ;;
    *) die 'usage: monitor enable|disable|once|status' ;;
  esac
}

tg_r2_json_array() {
  _tg_file=$1
  awk 'BEGIN{first=1;printf "["} NF {if (!first) printf ","; first=0;printf "\"%s\"",$0} END{printf "]"}' "$_tg_file"
}

tg_r2_json() {
  [ "$#" = 1 ] || die 'usage: json status|rules'
  tg_r2_init
  case "$1" in
    status)
      if [ -f "$TG_R2_ENABLED" ]; then _tg_enabled=true; else _tg_enabled=false; fi
      printf '{"schema":2,"monitor_enabled":%s,"interval_seconds":%s,"enrolled":' "$_tg_enabled" "$TG_R2_INTERVAL"
      tg_r2_json_array "$TG_R2_ENROLLED"
      printf ',"excluded":'
      tg_r2_json_array "$TG_R2_EXCLUDED"
      printf ',"auto_rules":%s,"total_rules":%s}\n' "$(wc -l < "$TG_R2_AUTO" | tr -d ' ')" "$(wc -l < "$TG_RULES" | tr -d ' ')" ;;
    rules)
      awk -F'|' '
        FILENAME==ARGV[1] { automatic[$0]=1; next }
        BEGIN { printf "["; first=1 }
        NF==3 {
          if (!first) printf ","; first=0
          printf "{\"package\":\"%s\",\"type\":\"%s\",\"component\":\"%s\",\"source\":\"%s\"}", $1,$2,$3, ($0 in automatic ? "auto":"manual")
        }
        END { printf "]\n" }
      ' "$TG_R2_AUTO" "$TG_RULES" ;;
    *) die 'usage: json status|rules' ;;
  esac
}

tg_r2_usage() {
  cat <<'HELP'
R2 additional TrackerGuard commands:
  bindhosts tracker monitor enable|disable|once|status
  bindhosts tracker enroll PACKAGE        # auto-block review-class receivers ONLY
  bindhosts tracker unenroll PACKAGE      # remove ONLY R2-owned auto rules
  bindhosts tracker exclude PACKAGE       # opt out and remove auto rules (manual unaffected)
  bindhosts tracker include PACKAGE       # remove exclusion, reconcile if enrolled
  bindhosts tracker reconcile PACKAGE     # rescan an enrolled app, fail-closed
  bindhosts tracker json status|rules     # machine-readable data
Default: monitor disabled, no enrolled apps, no automatic blocking.
HELP
}
