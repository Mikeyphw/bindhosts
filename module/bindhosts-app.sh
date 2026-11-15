#!/system/bin/sh
# Offline, embedded, byte-verified com.mikeyphw.bindhosts companion installer.
# Also invoked from the module WebUI. Never contacts a release API.
set -u
PATH=/system/bin:/system/xbin:/data/adb/ap/bin:/data/adb/ksu/bin:/data/adb/magisk:$PATH
APP_PACKAGE=com.mikeyphw.bindhosts
MODDIR=${MODPATH:-$(CDPATH= cd "$(dirname "$0")" && pwd -P)}
APK="$MODDIR/companion/bindhosts-companion.apk"
SHA="$MODDIR/companion/bindhosts-companion.sha256"

fail() { echo "BH_APP01_COMPANION_INSTALL_REFUSED: $1" >&2; exit 12; }
[ "$(id -u)" = 0 ] || fail ROOT_REQUIRED
[ -f "$APK" ] && [ ! -L "$APK" ] && [ -s "$APK" ] || fail EMBEDDED_APK_MISSING
[ -f "$SHA" ] && [ ! -L "$SHA" ] || fail EMBEDDED_SHA_MISSING
[ -x /system/bin/pm ] || command -v pm >/dev/null 2>&1 || fail PACKAGE_MANAGER_UNAVAILABLE
command -v sha256sum >/dev/null 2>&1 || fail SHA256SUM_UNAVAILABLE
expected=$(cat "$SHA") || fail SHA_READ_FAILED
case "$expected" in ''|*[!0123456789abcdef]*) fail INVALID_SHA_FORMAT ;; esac
[ "${#expected}" -eq 64 ] || fail INVALID_SHA_LENGTH
actual=$(sha256sum "$APK") || fail APK_SHA_READ_FAILED
actual=${actual%% *}
[ "$actual" = "$expected" ] || fail EMBEDDED_APK_SHA_MISMATCH

# Do not perform an unnecessary reinstall when the same APK is installed.
installed=$(pm path "$APP_PACKAGE" 2>/dev/null || :)
case "$installed" in
    package:/data/app/*/base.apk)
        installed_path=${installed#package:}
        if [ -f "$installed_path" ]; then
            current=$(sha256sum "$installed_path" 2>/dev/null || :)
            current=${current%% *}
            if [ "$current" = "$expected" ]; then
                echo '[+] bindhosts Companion already installed (identical verified APK)'
                echo 'BH_APP01_COMPANION_ALREADY_IDENTICAL'
                exit 0
            fi
        fi
        ;;
    '' ) : ;;
    * ) fail UNEXPECTED_EXISTING_PACKAGE_PATH ;;
esac

# Staging makes the APK readable by Android's package manager; never install
# from a user-writable Download directory and never delete the existing app.
stage=$(mktemp -d /data/local/tmp/bh-companion.XXXXXXXX) || fail TEMP_DIRECTORY_UNAVAILABLE
case "$stage" in /data/local/tmp/bh-companion.*) : ;; *) fail UNSAFE_TEMP_DIRECTORY ;; esac
trap 'rm -rf "$stage"' EXIT HUP INT TERM
chmod 0700 "$stage" || fail TEMP_PERMISSIONS_FAILED
cat "$APK" > "$stage/app.apk" || fail TEMP_COPY_FAILED
chmod 0644 "$stage/app.apk" || fail TEMP_APK_PERMISSIONS_FAILED
staged=$(sha256sum "$stage/app.apk") || fail TEMP_SHA_FAILED
[ "${staged%% *}" = "$expected" ] || fail TEMP_APK_SHA_MISMATCH
# Android will reject signature mismatches or disallowed downgrades; do NOT
# silently uninstall an existing package or bypass PackageManager protections.
if ! pm install -r "$stage/app.apk"; then
    fail PACKAGE_MANAGER_REFUSED_SIGNATURE_OR_VERSION
fi
installed=$(pm path "$APP_PACKAGE" 2>/dev/null || :)
case "$installed" in package:/data/app/*/base.apk) : ;; *) fail INSTALLED_PACKAGE_NOT_VERIFIED ;; esac
installed_path=${installed#package:}
installed_sha=$(sha256sum "$installed_path" 2>/dev/null || :)
[ "${installed_sha%% *}" = "$expected" ] || fail INSTALLED_APK_SHA_MISMATCH
echo '[+] bindhosts Companion Installed'
echo "BH_APP01_COMPANION_EMBEDDED_INSTALL_PASS package=$APP_PACKAGE sha256=$expected"
