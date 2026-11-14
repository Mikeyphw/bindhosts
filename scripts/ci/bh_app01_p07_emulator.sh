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
reportdir=android/companion/app/build/outputs/androidTest-results/connected
[[ -d $reportdir ]] || { echo 'BH_APP01_P07_REFUSED: instrumentation XML directory missing' >&2; exit 12; }
find "$reportdir" -type f -name '*.xml' -exec cp -- {} "$out"/ \;
[[ $(find "$out" -maxdepth 1 -name '*.xml' -type f | wc -l) -ge 1 ]] || {
  echo 'BH_APP01_P07_REFUSED: instrumentation XML absent' >&2; exit 12;
}
adb shell am start -n com.mikeyphw.bindhosts/.MainActivity
# Only the disposable emulator screenshot is captured; never a physical-device image.
adb exec-out screencap -p > "$out/api36-home.png"
[[ $(wc -c < "$out/api36-home.png") -gt 4096 ]] || {
  echo 'BH_APP01_P07_REFUSED: hosted screenshot missing or invalid' >&2; exit 12;
}
echo 'BH_APP01_P07_HOSTED_API36_JOURNEYS_EXECUTED'
