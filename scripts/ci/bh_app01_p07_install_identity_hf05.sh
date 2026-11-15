#!/usr/bin/env bash
# P07 HF05: restore the exact built app APK after connectedDebugAndroidTest.
# Android Gradle connected tests may uninstall the target app at teardown.
# Not for a physical device, not for local Gradle, not for release installation.
set -euo pipefail
refuse() { printf 'BH_APP01_P07_HF05_REFUSED_%s\n' "$1" >&2; exit 12; }
[[ $# -eq 2 ]] || refuse ARGUMENT_COUNT
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_OS:-} == Linux ]] || refuse NON_HOSTED_RUNNER
[[ ${SOURCE_SHA:-} =~ ^[0-9a-f]{40}$ ]] || refuse INVALID_SOURCE_SHA
[[ $(git rev-parse HEAD) == "$SOURCE_SHA" ]] || refuse HEAD_DRIFT
apk=$1;out=$2
[[ $apk == android/companion/app/build/outputs/apk/debug/app-debug.apk ]] || refuse APK_PATH
[[ $out == android/companion/p07-evidence ]] || refuse EVIDENCE_PATH
[[ -f $apk && ! -L $apk && -s $apk ]] || refuse APK_MISSING
[[ -d $out && ! -L $out ]] || refuse EVIDENCE_DIR
serial=emulator-5554
attached=$(adb devices -l | awk 'NR>1 && $2=="device" { print $1 }') || refuse DEVICE_DISCOVERY
[[ $attached == "$serial" ]] || refuse EXPECTED_SINGLE_EMULATOR
[[ $(adb -s "$serial" get-state | tr -d '\r') == device ]] || refuse EMULATOR_NOT_READY
[[ $(adb -s "$serial" shell getprop ro.kernel.qemu | tr -d '\r') == 1 ]] || refuse PHYSICAL_DEVICE
[[ $(adb -s "$serial" shell getprop ro.build.version.sdk | tr -d '\r') == 36 ]] || refuse WRONG_API
[[ $(adb -s "$serial" shell getprop ro.product.cpu.abi | tr -d '\r') == x86_64 ]] || refuse WRONG_ABI
apk_sha=$(sha256sum "$apk" | awk '{print $1}') || refuse APK_SHA_QUERY
[[ $apk_sha =~ ^[0-9a-f]{64}$ ]] || refuse APK_SHA_INVALID
[[ $(cat "$out/apk-sha256.txt") == "$apk_sha" ]] || refuse BUILT_HASH_MISMATCH
# The previous three connected tests and strict Lint have already completed.
# Re-install on the isolated emulator ONLY, then read the actual installed bytes.
install_output=$(adb -s "$serial" install -r -t "$apk") || refuse EMULATOR_INSTALL
[[ $install_output == *Success* ]] || refuse EMULATOR_INSTALL_RECEIPT
path_output=$(adb -s "$serial" shell pm path com.mikeyphw.bindhosts | tr -d '\r') || refuse INSTALLED_PACKAGE_QUERY
[[ $path_output == package:/data/app/*/base.apk ]] || refuse INSTALLED_PACKAGE_PATH
installed_path=${path_output#package:}
[[ $installed_path =~ ^/data/app/[A-Za-z0-9_./~+=-]+/base[.]apk$ ]] || refuse INSTALLED_PATH_UNSAFE
[[ $installed_path != *'/../'* ]] || refuse INSTALLED_PATH_TRAVERSAL
installed_sha=$(adb -s "$serial" shell sha256sum "$installed_path" | tr -d '\r' | awk '{print $1}') || refuse INSTALLED_SHA_QUERY
[[ $installed_sha =~ ^[0-9a-f]{64}$ ]] || refuse INSTALLED_SHA_INVALID
[[ $installed_sha == "$apk_sha" ]] || refuse INSTALLED_BYTES_MISMATCH
printf 'schema=bh-app01/p07/hf05\nsource_sha=%s\nemulator_api=36\nemulator_abi=x86_64\npackage=com.mikeyphw.bindhosts\napk_sha256=%s\ninstalled_sha256=%s\nphysical_device_writes=false\n' \
  "$SOURCE_SHA" "$apk_sha" "$installed_sha" > "$out/emulator-installed-identity.txt"
echo "BH_APP01_P07_HF05_DISPOSABLE_INSTALLED_APK_IDENTITY_PASS $SOURCE_SHA"
