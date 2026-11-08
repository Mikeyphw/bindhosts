#!/system/bin/sh
# SPDX-License-Identifier: MIT
# R1: read-only native AXML manifest inventory + opt-in batch IFW application.
# Sourced by module/trackerguard.sh after the R0 functions are declared.

TG_R1_MODDIR=${TG_R1_MODDIR:-/data/adb/modules/bindhosts}
TG_R1_SIGNATURES=${TG_R1_SIGNATURES:-$TG_R1_MODDIR/data/tracker-signatures.tsv}
TG_R1_BUSYBOX=${TG_R1_BUSYBOX:-busybox}

tg_r1_scanner() {
  if [ -n "${TG_R1_SCANNER:-}" ]; then
    [ -x "$TG_R1_SCANNER" ] || die "native scanner not executable: $TG_R1_SCANNER"
    printf '%s\n' "$TG_R1_SCANNER"
    return
  fi
  _tg_abi=$(getprop ro.product.cpu.abi)
  case "$_tg_abi" in arm64-v8a|armeabi-v7a|x86_64) :;; *) die "unsupported ABI: $_tg_abi" ;; esac
  _tg_bin="$TG_R1_MODDIR/bin/$_tg_abi/axmlscan"
  [ -x "$_tg_bin" ] || die "scanner missing for $_tg_abi (use full R1 CI ZIP)"
  printf '%s\n' "$_tg_bin"
}

tg_r1_matches() (
  [ "$#" -eq 1 ] || die 'usage: scan|preview|block PACKAGE'
  _tg_pkg=$1
  validate_package "$_tg_pkg"
  check_user_package "$_tg_pkg"
  [ -s "$TG_R1_SIGNATURES" ] || die "missing tracker signature database: $TG_R1_SIGNATURES"
  # For declared components we inspect the binary manifest actually in base.apk.
  # Split-manifest components are out of scope for R1, reported in docs.
  _tg_paths=$("$TG_PM" path "$_tg_pkg") || die 'pm path failed'
  _tg_apk=$(printf '%s\n' "$_tg_paths" | sed -n 's/^package://p' | grep '/base\.apk$' | head -n 1)
  [ -n "$_tg_apk" ] && [ -r "$_tg_apk" ] || die 'readable base.apk not found'
  _tg_scanner=$(tg_r1_scanner) || exit 1
  mkdir -p "$TG_STATE_DIR" || die 'cannot create state directory'
  chmod 700 "$TG_STATE_DIR" || die 'cannot secure state directory'
  _tg_raw=$(mktemp "$TG_STATE_DIR/r1.manifest.XXXXXXXX") || die 'cannot create private manifest temporary file'
  _tg_inventory=$(mktemp "$TG_STATE_DIR/r1.inventory.XXXXXXXX") || die 'cannot create private inventory temporary file'
  trap 'rm -f "$_tg_raw" "$_tg_inventory"' EXIT HUP INT TERM
  chmod 600 "$_tg_raw" "$_tg_inventory" || die 'cannot secure temporary files'
  if ! "$TG_R1_BUSYBOX" unzip -p "$_tg_apk" AndroidManifest.xml > "$_tg_raw"; then
    die 'could not extract AndroidManifest.xml from base.apk'
  fi
  if ! "$_tg_scanner" "$_tg_raw" > "$_tg_inventory"; then
    die 'invalid or unsupported Android binary manifest (no rules changed)'
  fi
  [ "$(sed -n '1p' "$_tg_inventory")" = "package|$_tg_pkg" ] || die 'manifest/package mismatch (no rules changed)'
  # The packaged signature file is curated from App Manager's GPLv3+ list.
  # Prefixes are literal anchored Java namespace prefixes, never substring patterns.
  awk -F '|' '
    FNR==NR {
      if ($0=="" || $0 ~ /^#/) next
      if (NF!=3 || $1 !~ /^[A-Za-z_][A-Za-z_0-9.]*\.$/ || $2 !~ /^[a-z0-9-]+$/ || $3 !~ /^(review|caution)$/) { invalid=1; next }
      pref[$1]=$2; risk[$1]=$3
      next
    }
    FNR==1 { next }
    $1=="component" && NF==4 {
      best=""; length_best=0
      for (p in pref) if (index($3,p)==1 && length(p)>length_best) { best=p; length_best=length(p) }
      if (best!="") print $2 "|" $3 "|" pref[best] "|" $4 "|" risk[best]
    }
    END { if (invalid) { print "TrackerGuard: invalid signature database" > "/dev/stderr"; exit 7 } }
  ' "$TG_R1_SIGNATURES" "$_tg_inventory"
)

tg_r1_scan() {
  [ "$#" -eq 1 ] || die 'usage: scan PACKAGE'
  say 'TYPE|COMPONENT|SIGNATURE|ENABLED|RISK'
  tg_r1_matches "$1"
}

tg_r1_preview() {
  [ "$#" -eq 1 ] || die 'usage: preview PACKAGE'
  mkdir -p "$TG_STATE_DIR" || die 'cannot create private state directory'
  chmod 700 "$TG_STATE_DIR" || die 'cannot secure private state directory'
  _tg_previewfile=$(mktemp "$TG_STATE_DIR/r1.preview.XXXXXXXX") || die 'cannot create preview temporary file'
  chmod 600 "$_tg_previewfile" || die 'cannot secure preview temporary file'
  if ! tg_r1_matches "$1" > "$_tg_previewfile"; then
    rm -f "$_tg_previewfile"
    die 'scan failed; no IFW rules changed'
  fi
  say 'PREVIEW ONLY: no IFW or package changes'
  say 'TYPE|COMPONENT|SIGNATURE|ENABLED|RISK|ACTION'
  while IFS='|' read -r _tg_type _tg_cls _tg_sig _tg_enabled _tg_risk; do
    case "$_tg_type:$_tg_enabled" in
      provider:*) _tg_action=info-only-provider ;;
      *:false) _tg_action=already-disabled ;;
      service:true|receiver:true|activity:true) _tg_action=would-block ;;
      *) _tg_action=unsupported ;;
    esac
    printf '%s|%s|%s|%s|%s|%s\n' "$_tg_type" "$_tg_cls" "$_tg_sig" "$_tg_enabled" "$_tg_risk" "$_tg_action"
  done < "$_tg_previewfile"
  rm -f "$_tg_previewfile"
}

tg_r1_block() {
  [ "$#" -eq 1 ] || die 'usage: block PACKAGE'
  validate_package "$1"
  _tg_blockpkg=$1
  mkdir -p "$TG_STATE_DIR" || die 'cannot create private state directory'
  chmod 700 "$TG_STATE_DIR" || die 'cannot secure private state directory'
  _tg_matchfile=$(mktemp "$TG_STATE_DIR/r1.matches.XXXXXXXX") || die 'cannot create scan result temporary file'
  chmod 600 "$_tg_matchfile" || die 'cannot secure scan result temporary file'
  if ! tg_r1_matches "$_tg_blockpkg" > "$_tg_matchfile"; then
    rm -f "$_tg_matchfile"
    die 'scan failed; no IFW rules changed'
  fi
  _tg_count=$(awk -F'|' '$4=="true" && ($1=="service" || $1=="receiver" || $1=="activity") { n++ } END { print n+0 }' "$_tg_matchfile")
  [ "$_tg_count" -gt 0 ] || { rm -f "$_tg_matchfile"; say 'No eligible enabled tracker components; no changes'; return 0; }
  prepare; lock; check_owned
  _tg_pending="$TG_STATE_DIR/rules.$$.pending"
  cat "$TG_RULES" > "$_tg_pending" || die 'cannot copy current rules'
  while IFS='|' read -r _tg_kind _tg_class _tg_sig _tg_enabled _tg_risk; do
    [ "$_tg_enabled" = true ] || continue
    case "$_tg_kind" in service|receiver|activity) : ;; *) continue ;; esac
    validate_type "$_tg_kind"
    _tg_normal=$(normalize_class "$_tg_blockpkg" "$_tg_class") || die 'invalid scanner class'
    [ "$_tg_normal" = "$_tg_class" ] || die 'noncanonical component class'
    printf '%s|%s|%s\n' "$_tg_blockpkg" "$_tg_kind" "$_tg_class" >> "$_tg_pending" || die 'cannot stage rule'
  done < "$_tg_matchfile"
  LC_ALL=C sort -u "$_tg_pending" -o "$_tg_pending" || die 'cannot deduplicate pending rules'
  # R0 write_rules atomically writes ONLY our own IFW file, then commits state.
  write_rules "$_tg_pending"
  rm -f "$_tg_matchfile"
  say "Installed opt-in IFW rules for $_tg_blockpkg (device enforcement unverified)"
  say 'Restore: bindhosts tracker restore PACKAGE'
}
