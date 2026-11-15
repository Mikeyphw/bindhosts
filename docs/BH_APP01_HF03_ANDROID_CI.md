# BH-APP01 HF03 — hosted Android SDK setup repair

## Failure evidence

GitHub run [43614339186](https://github.com/Mikeyphw/bindhosts/actions/runs/43614339186), source SHA `39b3493c4b070b5be22278983014a1ffcfa4c536`:
- `source` job passed.
- `android` failed at `android-actions/setup-android@v3` before Gradle started.
- SDK manager attempted the removed legacy package `tools`, reported `Warning: Failed to find package 'tools'`, and returned exit 1.
- Gradle, SDK installation, APK and upload steps were skipped.

## Fix

Remove `android-actions/setup-android@v3` and invoke the preinstalled cmdline-tools SDK manager directly to install `platforms;android-36` and `build-tools;36.0.0`. Accept SDK licenses with explicit sdkmanager exit-status checking, avoiding false SIGPIPE failures from `yes`. Require an actual `android.jar` and executable `aapt2` before Gradle. A missing SDK manager, unsuccessful installation, or missing outputs fails visibly. No legacy `tools` package is requested. The exact CI branch must be updated with a new commit; rerunning an unchanged failed SHA will reproduce the failure.

## Evidence gate

Unit tests run with fake sdkmanager (success/failure/license refusal/missing outputs); source tests remain unchanged. Gradle runs exclusively in GitHub Actions. An actual successful Android job and uploaded APK at the new SHA, plus later physical Android 16 verification, are still required. An SDK setup pass alone is not APK qualification.
