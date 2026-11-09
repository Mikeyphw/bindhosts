# TrackerGuard R3 — isolated Android 16 lifecycle qualification

Source baseline: UX06 PR #10 head `2b28f140c817491cfa5dd312139765bbebf767af`; target v2.1.5-tg.0.10 (21610). **This milestone is a device-qualification harness, not a widening of automatic blocking.** All production R2 rules remain receiver-only and opt-in.

## Test boundaries

- `module/data/r3-lab-signatures.tsv` is a dedicated **test-only signature**. The normal `tracker-signatures.tsv` does **not** reference the lab receiver. R3 injects the lab signature through the `TG_R1_SIGNATURES` environment variable for explicit acceptance commands only.
- The debug lab is an isolated app with a single exported receiver and **no Internet permissions**. Hosted GitHub Actions builds two versions with identical package IDs and versionCodes 1 and 2. It does **not** compile Gradle on Termux.
- `tests/trackerguard-r3/run_device_acceptance.py` requires local `aapt`/`aapt2` to verify the package ID, exact v1/v2 versionCode and absence of declared permissions **before installation**, then checks an available rooted adb device, refuses if the lab app already exists, refuses active R2 monitoring or other enrolled/auto apps, and preserves all pre-existing manual IFW rules. It never runs `restore --all`.
- Only `--read-only` may be run without authorization; `--run --accept-device-writes` is required for every install/update/uninstall/IFW phase.
- Explicit lifecycle: install v1, verify receiver delivers, enroll lab using the test signature, verify IFW blocks delivery, install v2, reconcile and confirm receiver is still blocked, uninstall and verify automatic-prune, reinstall v2 and verify auto-blocking again, unenroll and confirm receiver delivery is restored, then disable/uninstall and verify original manual+auto+enrolled+excluded bytes.
- R2 `seen.tsv` is allowed to advance because the test intentionally takes package snapshots. The harness first seeds v1 before checking the v2 **updated** event, and verifies that the final `seen.tsv` no longer includes the removed lab package. `monitor.log` may retain private diagnostic evidence of the test; these files are not byte-for-byte restored. The script does not write arbitrary state files. On a failed cleanup, it prints a specific failure and refuses a success marker. Device interruption/power failure can still require manual inspection.
- Runtime acceptance is **not** established by CI alone. GitHub Actions validates the harness with mocked adb, builds both APKs, compiles the module and runs existing R0-R2/UX01-UX06 tests. The Android 16 test must still run on a physical rooted device.

## Run on Termux (after module installation and reboot)

Ensure Android BuildTools `aapt` is available in Termux; the write test refuses to run without metadata verification. Download two APK artifacts from the successful `TrackerGuard IFW runtime lab APK` GitHub Actions run: `trackerguard-ifw-lab-v1` and `trackerguard-ifw-lab-v2`. Extract them under `$TMPDIR` or provide their existing paths.

Read-only, no app/package/IFW mutations:

```zsh
python3 tests/trackerguard-r3/run_device_acceptance.py --serial localhost:5555 --read-only
```

**Explicit opt-in live test (installs, upgrades and removes the dedicated lab APK):**

```zsh
python3 tests/trackerguard-r3/run_device_acceptance.py --serial localhost:5555 --run --accept-device-writes \
  --apk-v1 "$TMPDIR/trackerguard-r3-lab/lab-v1.apk" \
  --apk-v2 "$TMPDIR/trackerguard-r3-lab/lab-v2.apk"
```

The test refuses to run if the dedicated app already exists or other R2 automatic rules/enrollment could be affected. `TG_R3_LIVE_ACCEPTANCE_PASS` is the final success marker. If a rollback failure occurs, check `tracker json status`, `tracker json rules` and the lab package before taking additional action.

## R3 HF01 completion audit

- Fixes the first-snapshot blind spot before testing the v2 package update.
- Checks the observer snapshot after cleanup, in addition to manual/auto rule bytes.
- `service.sh` attempts pending hosts journal recovery before mounting the managed module hosts file in modes 0–6,9–10. Overlay modes 7/8 require mounting the overlay first and recover immediately afterwards; a failure stops further services. The overlay modes cannot guarantee no early exposure of incomplete hosts bytes.
- Does **not** claim SELinux, WebUI, live HTTP image-mode, UX05/UX06 device acceptance, or R3 lifecycle qualification from offline tests.
- Guards `post-fs-data.sh` first-time hosts initialization: the append uses the managed module target, never an unbound `$MODPATH` environment variable.
- Asserts receiver denial *after updating v1 to v2*, then proves receiver delivery returns after explicit unenrollment.
