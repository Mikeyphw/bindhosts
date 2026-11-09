# TrackerGuard R3 HF02 — Android 16 PackageManager snapshot recovery

**Observed failure:** `TG_R3_BASELINE_DELIVERY_PASS` followed by `TrackerGuard: package snapshot failed; state retained`, and a misleading `TG_R3_CLEANUP_FAILED reconcile`.

## What this changes

- `trackerguard_r2.sh` now reports redacted, differentiated root PackageManager query, parse, and normalization failures. Falls back to `cmd package` **only when** `pm` itself returns a failure. No auto-enrollment, no IFW write, and no partial package snapshots on error.
- Snapshot parser permits `/data/app/~~...==/...==/base.apk=` paths, explicitly validates the final package segment and version code, and rejects bad records or duplicate packages. It does not silently drop malformed records, treat an empty list as uninstall, or include package names in error logs.
- R3 harness skips redundant cleanup `monitor once` after its *first* snapshot has failed. It still attempts to uninstall its own lab APK and compare manual/auto/enrollment/exclusion state to original bytes. If cleanup genuinely differs, it still fails.
- New focused tests check healthy Android 16 output, known optional PackageManager metadata, malformed/empty snapshots, PM command fallback, and the first-snapshot-failure cleanup path.

## Important qualification gap

The device's actual root PackageManager output is **not yet available**. This is a diagnostic, compatibility and cleanup fix, not proof that your device's exact PM failure has been cured. It never changes existing TrackerGuard rules to work around unknown output.

Use the kit's `DIAGNOSE.zsh` for a **read-only, redacted** PackageManager diagnosis before attempting a new live test. On a failed initial snapshot, the harness did not reach R3 auto-enrollment, so a lab receiver rule should not have been created; verify state before retrying.

## No branch merges

R3 PR #11 remains unqualified. The HF02 installer updates the exact UX07 PR #12 branch and watches focused module CI; it does **not** merge PR #11 or #12.
