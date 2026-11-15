#!/system/bin/sh
# BH-APP01 P04B P03: finite UX06/UX05/UX07 native actions.
# Each request is one ASCII base64 data argument. No arbitrary paths or shell.
set -eu
set -f
umask 077
refuse() { printf 'BH_APP01_V5_REFUSED: %s\n' "$1" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse 'expected subsystem and encoded action'
SUBSYSTEM=$1; TOKEN=$2
case "$SUBSYSTEM" in backup|diagnostics|response) : ;; *) refuse 'unknown subsystem' ;; esac
case "$TOKEN" in ''|*[!A-Za-z0-9+/=]*) refuse 'invalid request encoding' ;; esac
[ "${#TOKEN}" -le 320 ] || refuse 'oversized request'
# Inspect raw decoded bytes before shell substitution can discard NUL/controls.
CONTROL_BYTES=$(printf '%s' "$TOKEN" | base64 -d 2>/dev/null | LC_ALL=C tr -cd '\000-\037\177' | wc -c) || refuse 'invalid request bytes'
case "$CONTROL_BYTES" in ''|*[!0-9]*) refuse 'invalid control-byte count' ;; esac
[ "$CONTROL_BYTES" -eq 0 ] || refuse 'control characters in encoded input'
ACTION=$(printf '%s' "$TOKEN" | base64 -d 2>/dev/null) || refuse 'invalid action base64'
case "$ACTION" in ''|*[!A-Za-z0-9_.~-]*) refuse 'unsupported action characters' ;; esac
[ "${#ACTION}" -le 160 ] || refuse 'oversized action'
case "$ACTION" in *..*) refuse 'parent traversal' ;; esac
if [ "${BH_APP01_V5_TEST_MODE:-0}" = 1 ]; then
  [ "$(id -u)" -ne 0 ] || refuse 'rooted fixture refused'
  MODDIR=${BH_APP01_V5_TEST_MODDIR:-}; STATE=${BH_APP01_V5_TEST_STATE:-}
  [ -n "$MODDIR" ] && [ -n "$STATE" ] || refuse 'incomplete fixture'
else
  [ -z "${BH_APP01_V5_TEST_MODDIR:-}" ] && [ -z "${BH_APP01_V5_TEST_STATE:-}" ] || refuse 'production fixture override'
  [ "$(id -u)" = 0 ] || refuse 'root required'
  MODDIR=/data/adb/modules/bindhosts; STATE=/data/adb/bindhosts
fi
[ -d "$MODDIR" ] && [ ! -L "$MODDIR" ] && [ -d "$STATE" ] && [ ! -L "$STATE" ] || refuse 'unsafe root directories'
require_backend() { [ -f "$MODDIR/$1" ] && [ ! -L "$MODDIR/$1" ] || refuse 'missing/unsafe backend'; }
valid_snapshot() { printf '%s' "$1" | LC_ALL=C grep -Eq '^bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$' || refuse 'invalid snapshot'; }
valid_archive() { printf '%s' "$1" | LC_ALL=C grep -Eq '^bindhosts-backup-bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}\.tar$' || refuse 'invalid archive name'; }
TMP=$(mktemp "$STATE/.bh-app01-v5.XXXXXXXX") || refuse 'cannot allocate private response'
trap 'rm -f "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
case "$SUBSYSTEM" in
  backup)
    require_backend config_backup_safe.sh
    case "$ACTION" in
      create) sh "$MODDIR/config_backup_safe.sh" create > "$TMP" 2>/dev/null || refuse 'backup create failed' ;;
      restore~*|export~*)
        VERB=${ACTION%%~*}; SNAP=${ACTION#*~}; valid_snapshot "$SNAP"
        sh "$MODDIR/config_backup_safe.sh" "$VERB" "$SNAP" > "$TMP" 2>/dev/null || refuse 'backup action failed' ;;
      import~*)
        NAME=${ACTION#import~}; valid_archive "$NAME"
        sh "$MODDIR/config_backup_safe.sh" import "$NAME" > "$TMP" 2>/dev/null || refuse 'backup import failed' ;;
      *) refuse 'unsupported backup mutation' ;;
    esac
    case "$ACTION" in
      create) grep -Eq '^BH_BACKUP_CREATED: bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$' "$TMP" || refuse 'missing create receipt' ;;
      restore~*) grep -Fxq "BH_BACKUP_RESTORE_PASS: $SNAP" "$TMP" || refuse 'missing restore receipt' ;;
      export~*) grep -Eq '^BH_BACKUP_EXPORTED: /storage/emulated/0/Download/bindhosts-backup-bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}\.tar$' "$TMP" || refuse 'missing export receipt' ;;
      import~*) grep -Eq '^BH_BACKUP_IMPORTED: bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$' "$TMP" || refuse 'missing import receipt' ;;
    esac ;;
  diagnostics)
    require_backend ux05_diagnostics.sh
    [ "$ACTION" = export ] || refuse 'unsupported diagnostics mutation'
    sh "$MODDIR/ux05_diagnostics.sh" export > "$TMP" 2>/dev/null || refuse 'redacted diagnostics export refused'
    grep -Eq '^BH_UX05_EXPORT_PATH=/storage/emulated/0/Download/bindhosts_diagnostics_[A-Za-z0-9_]+\.json$' "$TMP" || refuse 'missing redacted export receipt' ;;
  response)
    require_backend bindhosts.sh
    case "$ACTION" in
      set~off|set~transparent|set~logo)
        MODE=${ACTION#set~}
        sh "$MODDIR/bindhosts.sh" --response set "$MODE" > "$TMP" 2>/dev/null || refuse 'response mode change refused'
        grep -Eq "^BH_RESPONSE_(MODE_PASS: $MODE|MODE_UNCHANGED|SERVER_REPAIRED)$" "$TMP" || refuse 'response mode unverified' ;;
      https~cert-create|https~cert-export|https~enable|https~disable|https~test)
        HTTPS=${ACTION#https~}
        sh "$MODDIR/bindhosts.sh" --response https "$HTTPS" > "$TMP" 2>/dev/null || refuse 'HTTPS action refused'
        case "$HTTPS" in
          cert-create) grep -Fxq 'BH_HTTPS_CERT_INSTALL_IS_MANUAL' "$TMP" || refuse 'CA creation receipt missing' ;;
          cert-export) grep -Fxq 'BH_HTTPS_CA_INSTALL_REQUIRES_ANDROID_USER_ACTION' "$TMP" || refuse 'CA public export receipt missing' ;;
          enable) grep -Eq '^BH_HTTPS_(ENABLED_ANDROID_TRUST_UNVERIFIED|ALREADY_ENABLED)$' "$TMP" || refuse 'TLS enable receipt missing' ;;
          disable) grep -Fxq 'BH_HTTPS_DISABLED_CA_REMAINS_INSTALLED_IF_USER_ADDED_IT' "$TMP" || refuse 'TLS disable receipt missing' ;;
          test) grep -Fxq 'BH_HTTPS_LOCAL_TLS_PASS_ANDROID_TRUST_UNVERIFIED' "$TMP" || refuse 'TLS local test receipt missing' ;;
        esac ;;
      *) refuse 'unsupported response mutation' ;;
    esac ;;
esac
SIZE=$(wc -c < "$TMP" | tr -d ' ')
case "$SIZE" in ''|*[!0-9]*) refuse 'invalid output size' ;; esac
[ "$SIZE" -le 4000 ] || refuse 'oversized backend receipt'
ENC=$(base64 < "$TMP" | tr -d '\r\n') || refuse 'cannot encode safe reply'
case "$ENC" in *[!A-Za-z0-9+/=]*) refuse 'invalid base64 reply' ;; esac
printf '{"api":5,"action":"%s","encoded":"%s"}\n' "$SUBSYSTEM" "$ENC"
