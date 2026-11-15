# BH-APP01 P07 HF05 — Hosted APK reinstall + installed binary identity

**PR:** `Mikeyphw/bindhosts` #19, **exact parent HEAD:** `da7fa5b9bf67353eff6f4c4307e63a272c3bbd32`.

**Failed HF04 runs:** pull request `43665454496`, push `43665448413`.

## Evidence and root cause

Hosted Android API36 x86_64 emulator and the Android/Gradle instrumentation ran successfully. Push run `43665448413` reports **3/3 tests completed, zero skipped and zero failed**, followed by `BUILD SUCCESSFUL`. The uploaded failure artifact contains a valid APK hash, an AndroidJUnit XML report, and `qs-cold-start-am.txt` with:

```text
Starting: Intent { act=com.mikeyphw.bindhosts.CONFIRM_UPDATE cmp=com.mikeyphw.bindhosts/.MainActivity }
Error type 3
Error: Activity class {com.mikeyphw.bindhosts/com.mikeyphw.bindhosts.MainActivity} does not exist.
```

Android Gradle connected instrumentation can remove the target app after test teardown. HF04's separate ADB QS cold-start test assumed it remained installed. This is a **post-instrumentation APK lifecycle** failure, not a QS modal regression.

## HF05 consolidated fix

- Adds a fail-closed exact-source `scripts/ci/bh_app01_p07_install_identity_hf05.sh` step **after** the real `connectedDebugAndroidTest`, **before** the real QS cold-start intent.
- Checks GitHub-hosted runner, exact HEAD, exactly one `emulator-5554`, `ro.kernel.qemu=1`, API36 and x86_64. Does not connect to or modify a physical Android device.
- Reinstalls the exact debug APK just built on the disposable emulator (`adb -s emulator-5554 install -r -t`). Reads the actual installed APK path using `pm path`, then **hashes the installed `base.apk`** using `sha256sum` and compares against the GitHub build's local SHA-256. Rejects installation, unsafe paths, missing packages and mismatch before any QS cold-start action.
- Saves `emulator-installed-identity.txt`, tied to exact source SHA and both matching APK hashes. The P07 signoff verifier now rejects missing, altered, or unverified installed identity evidence.
- Retains all three unskipped Android instrumentation cases, strict Lint, the real ADB `am force-stop` / `am start -W` / UIAutomator dialog-and-Cancel test, screenshots, native events and four required workflows.
- New synthetic unprivileged regression fixtures exercise successful install and refusal for non-emulator, missing package, install failure, byte mismatch and source SHA drift; tests never invoke real adb.

**No local Gradle. No physical-device write acceptance. No release qualification.** Hosted HF05 CI must still prove actual behavior.
