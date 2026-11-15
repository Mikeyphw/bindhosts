#!/usr/bin/env bash
# BH-APP01 HF03: use the cmdline-tools already present on ubuntu-latest.
# android-actions/setup-android@v3 calls `sdkmanager tools`, removed from the
# current Android SDK repository. Do not request that obsolete SDK package.
set -euo pipefail
root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/usr/local/lib/android/sdk}}"
if [[ ! -d "$root" || -L "$root" ]]; then
  echo 'BH_APP01_ANDROID_SDK_REFUSED: SDK root missing or unsafe' >&2
  exit 2
fi
if [[ ! -d "$root/cmdline-tools" ]]; then
  echo 'BH_APP01_ANDROID_SDK_REFUSED: preinstalled cmdline-tools missing' >&2
  exit 2
fi
manager=''
# Prefer the hosted image latest tools; otherwise select the newest installed
# executable. Do not download/update the cmdline-tools package during CI.
if [[ -x "$root/cmdline-tools/latest/bin/sdkmanager" ]]; then
  manager="$root/cmdline-tools/latest/bin/sdkmanager"
else
  while IFS= read -r candidate; do
    if [[ -x "$candidate" ]]; then manager="$candidate"; fi
  done < <(find "$root/cmdline-tools" -mindepth 3 -maxdepth 3 -type f -name sdkmanager | LC_ALL=C sort -V)
fi
if [[ -z "$manager" ]]; then
  echo 'BH_APP01_ANDROID_SDK_REFUSED: no executable sdkmanager in cmdline-tools' >&2
  exit 2
fi
echo "BH_APP01_ANDROID_SDK_MANAGER=$manager"
# A fresh hosted runner must not depend on licenses accepted by a preceding
# action. `yes` can exit with SIGPIPE after sdkmanager finishes, so check the
# consumer exit status explicitly instead of treating SIGPIPE as SDK failure.
set +e
yes | "$manager" --sdk_root="$root" --licenses >/dev/null 2>&1
license_rc=${PIPESTATUS[1]}
set -e
if [[ "$license_rc" -ne 0 ]]; then
  echo 'BH_APP01_ANDROID_SDK_REFUSED: SDK license acceptance failed' >&2
  exit 2
fi
"$manager" --sdk_root="$root" --install 'platforms;android-36' 'build-tools;36.0.0'
if [[ ! -f "$root/platforms/android-36/android.jar" ]]; then
  echo 'BH_APP01_ANDROID_SDK_REFUSED: android-36/android.jar missing after installation' >&2
  exit 2
fi
if [[ ! -x "$root/build-tools/36.0.0/aapt2" ]]; then
  echo 'BH_APP01_ANDROID_SDK_REFUSED: build-tools 36.0.0/aapt2 missing after installation' >&2
  exit 2
fi
printf 'BH_APP01_ANDROID_SDK36_READY sdk_root=%s\n' "$root"
