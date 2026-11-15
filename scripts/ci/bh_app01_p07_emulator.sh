#!/usr/bin/env bash
# Must run ONLY in GitHub Actions, inside a disposable API36 emulator.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_OS:-} == Linux ]] || {
  echo 'BH_APP01_P07_REFUSED: disposable GitHub-hosted runner required' >&2; exit 12;
}
[[ ${SOURCE_SHA:-} =~ ^[0-9a-f]{40}$ ]] || {
  echo 'BH_APP01_P07_REFUSED: missing exact source SHA' >&2; exit 12;
}
[[ $(git rev-parse HEAD) == "$SOURCE_SHA" ]] || {
  echo 'BH_APP01_P07_REFUSED: exact HEAD mismatch' >&2; exit 12;
}
[[ $(adb devices -l | grep -c ' device ' || :) == 1 ]] || {
  echo 'BH_APP01_P07_REFUSED: expected exactly one disposable emulator' >&2; exit 12;
}
[[ $(adb shell getprop ro.build.version.sdk | tr -d '\r') == 36 ]] || {
  echo 'BH_APP01_P07_REFUSED: device is not API36' >&2; exit 12;
}
[[ $(adb shell getprop ro.product.cpu.abi | tr -d '\r') == x86_64 ]] || {
  echo 'BH_APP01_P07_REFUSED: expected hosted x86_64 emulator' >&2; exit 12;
}
out=android/companion/p07-evidence
mkdir -p "$out"
printf '%s\n' "$SOURCE_SHA" > "$out/source-commit.txt"
printf '%s\n' 36 > "$out/emulator-api.txt"
# Preserve instrumentation diagnostics even when Gradle/Android tests fail.
# The failure evidence is NEVER accepted by the hosted signoff verifier.
collect_failure_evidence() {
  local status=$?
  trap - EXIT
  set +e
  if (( status != 0 )); then
    printf '%s\n' "$status" > "$out/failed-command-exit.txt"
    reportdir=android/companion/app/build/outputs/androidTest-results/connected
    if [[ -d $reportdir ]]; then
      find "$reportdir" -type f -name '*.xml' -exec cp -- {} "$out"/ \;
    fi
    # Bounded logs from the disposable emulator only, not a user device.
    adb logcat -d -t 1600 -v threadtime \
      -s AndroidRuntime:E ActivityTaskManager:W ActivityManager:W TestRunner:I \
      > "$out/emulator-failure-logcat.txt" 2>&1
    adb exec-out screencap -p > "$out/api36-failure.png" 2>/dev/null
    if [[ ! -s "$out/api36-failure.png" ]]; then rm -f "$out/api36-failure.png"; fi
    echo "BH_APP01_P07_HF01_HOSTED_FAILURE_EVIDENCE_CAPTURED exit=$status" >&2
  fi
  exit "$status"
}
trap collect_failure_evidence EXIT
# Gradle is forbidden on local devices. This script refuses non-GitHub execution.
gradle -p android/companion --no-daemon \
  :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug :app:connectedDebugAndroidTest
apk=android/companion/app/build/outputs/apk/debug/app-debug.apk
[[ -s $apk ]] || { echo 'BH_APP01_P07_REFUSED: APK absent' >&2; exit 12; }
sha256sum "$apk" | awk '{print $1}' > "$out/apk-sha256.txt"
# connectedDebugAndroidTest may uninstall the target APK at teardown.
# HF04 proved 3/3 UI tests and Lint passed, but cold-start am returned Error type 3.
# Restore ONLY on a verified disposable emulator and verify the installed bytes.
bash scripts/ci/bh_app01_p07_install_identity_hf05.sh "$apk" "$out"
# PH02: retain the exact APK that passed these hosted instrumentation tests.
# Do not substitute a separately compiled debug APK with another signing key.
cp -- "$apk" "$out/hosted-app-debug.apk"
chmod 0600 "$out/hosted-app-debug.apk"
[[ $(sha256sum "$out/hosted-app-debug.apk" | awk '{print $1}') == $(cat "$out/apk-sha256.txt") ]] || {
  echo 'BH_APP01_P07_PH02_REFUSED: exported hosted APK bytes differ from tested APK' >&2
  exit 12
}
reportdir=android/companion/app/build/outputs/androidTest-results/connected
[[ -d $reportdir ]] || { echo 'BH_APP01_P07_REFUSED: instrumentation XML directory missing' >&2; exit 12; }
find "$reportdir" -type f -name '*.xml' -exec cp -- {} "$out"/ \;
[[ $(find "$out" -maxdepth 1 -name '*.xml' -type f | wc -l) -ge 1 ]] || {
  echo 'BH_APP01_P07_REFUSED: instrumentation XML absent' >&2; exit 12;
}
# A separate, true cold-start QS intent is required: ActivityScenario.launch
# with a custom action timed out at PRE_ON_CREATE despite normal launch passing.
# This test uses the system ActivityManager and reads the actual UI hierarchy.
adb shell am force-stop com.mikeyphw.bindhosts
adb logcat -c
adb shell am start -W -n com.mikeyphw.bindhosts/.MainActivity \
  -a com.mikeyphw.bindhosts.CONFIRM_UPDATE > "$out/qs-cold-start-am.txt"
[[ $(cat "$out/qs-cold-start-am.txt") == *'Status: ok'* ]] || {
  echo 'BH_APP01_P07_HF02_REFUSED: cold-start am launch did not report Status ok' >&2; exit 12;
}
confirmed=0
for attempt in $(seq 1 12); do
  # Dump is an emulator-only read. Do not assume a dialog exists from its intent.
  if timeout 15s adb shell uiautomator dump /sdcard/bh-app01-p07-hf02.xml >/dev/null 2>&1; then
    adb exec-out cat /sdcard/bh-app01-p07-hf02.xml > "$out/qs-cold-start-hierarchy.xml" || :
    if python3 scripts/ci/bh_app01_p07_qs_hierarchy.py \
        --hierarchy "$out/qs-cold-start-hierarchy.xml" --action verify; then
      confirmed=1; break
    fi
  fi
  sleep 2
done
[[ $confirmed == 1 ]] || {
  echo 'BH_APP01_P07_HF02_REFUSED: real cold-start QS dialog not observed' >&2; exit 12;
}
adb exec-out screencap -p > "$out/api36-qs-confirmation.png"
[[ $(wc -c < "$out/api36-qs-confirmation.png") -gt 4096 ]] || {
  echo 'BH_APP01_P07_HF02_REFUSED: QS screenshot absent or invalid' >&2; exit 12;
}
# Tap the actual Cancel bounds from the UI hierarchy, never the Update button.
read -r x y < <(python3 scripts/ci/bh_app01_p07_qs_hierarchy.py \
    --hierarchy "$out/qs-cold-start-hierarchy.xml" --action cancel-coordinates)
[[ $x =~ ^[0-9]{1,5}$ && $y =~ ^[0-9]{1,5}$ ]] || exit 12
adb shell input tap "$x" "$y"
for attempt in $(seq 1 12); do
  adb logcat -d -s BH_APP01_P07:I > "$out/qs-cold-start-logcat.txt"
  if grep -Fq 'QS_CONFIRM_INTENT_ACCEPTED' "$out/qs-cold-start-logcat.txt" &&
     grep -Fq 'QS_CONFIRM_DIALOG_VISIBLE' "$out/qs-cold-start-logcat.txt" &&
     grep -Fq 'QS_CONFIRM_CANCELLED' "$out/qs-cold-start-logcat.txt"; then
    break
  fi
  sleep 1
done
for token in QS_CONFIRM_INTENT_ACCEPTED QS_CONFIRM_DIALOG_VISIBLE QS_CONFIRM_CANCELLED; do
  grep -Fq "$token" "$out/qs-cold-start-logcat.txt" || {
    echo "BH_APP01_P07_HF02_REFUSED: missing native event $token" >&2; exit 12;
  }
done
# Confirm explicit Cancel did not close the app, rather than merely making
# the dialog disappear while the app crashes or returns to the launcher.
state=$(adb shell dumpsys activity activities)
[[ "$state" == *'com.mikeyphw.bindhosts/.MainActivity'* ]] || {
  echo 'BH_APP01_P07_HF02_REFUSED: activity missing after Cancel' >&2; exit 12;
}
printf 'schema=bh-app01/p07/hf02\nsource_sha=%s\nemulator_api=36\ncold_start_confirm=PASS\nqs_cancel=PASS\nphysical_device_writes=false\n' \
    "$SOURCE_SHA" > "$out/qs-cold-start-receipt.txt"
# Original hosted screenshot and exact-SHA signoff remain mandatory.
adb exec-out screencap -p > "$out/api36-home.png"
[[ $(wc -c < "$out/api36-home.png") -gt 4096 ]] || {
  echo 'BH_APP01_P07_REFUSED: hosted screenshot missing or invalid' >&2; exit 12;
}
echo 'BH_APP01_P07_HOSTED_API36_JOURNEYS_EXECUTED'
