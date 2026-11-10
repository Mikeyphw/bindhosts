# TrackerGuard R3 HF03 — fingerprint continuity and ZIP-embedded Python launcher

## Changes from HF02

HF02's PackageManager parser accidentally added `package:` to the fingerprint stored in `seen.tsv`. Pre-HF02 fingerprints used the APK path without the prefix. This could classify unchanged installed packages as updated and reconcile already enrolled apps. HF03 restores the exact historical fingerprint shape, while retaining HF02's fail-closed parsing, command fallback and redacted error reports.

The focused HF02 parser suite is now an explicit command in the native module workflow. A new byte-exact regression test checks legacy `seen.tsv` compatibility and blocks silent drift. This test is run locally before commit and again by hosted CI.

## Single-file launcher

The complete launcher is the ZIP itself, using Python's ZIP-app `__main__.py` feature:

```sh
python3 /sdcard/Download/Bindhosts_TrackerGuard_R3_HF03_Python_Rich_Executable_Overlay.zip
```

No standalone Python file is needed; `rich` must be installed into the invoking Python. The ZIP offers `verify`, `self-test`, `audit`, `diagnose`, `apply`, and `ci` commands. `python3 overlay.zip` with no arguments displays a menu in an interactive Termux shell. The package does not extract its code to device storage; temporary regression tests use `$TMPDIR` only.

## Safe execution order

1. `self-test`: offline parser regression checks with fake PackageManager data, with no real device calls.
2. `diagnose`: read-only Android PackageManager and root state fingerprint inspection. Ensure the lab APK is confirmed absent and no lab IFW rules remain; compare reported hashes to an independently trusted baseline to confirm the **original** rules remain intact.
3. `audit` and `apply`: exact current PR #12 source pins, clean checkout and existing PR branch checked before any code edit. Local offline suites must pass. `apply` commits and pushes only the intended files; there is no auto-merge, Android write or background CI watcher.
4. `ci`: one immediate exact-commit hosted module workflow check. A pending result is *not* qualification.
5. Only after all gates and device inspection, obtain the new hosted module ZIP, install it, reboot, then perform separately authorized R3 live acceptance.

There is no historical reference hash bundled in this overlay; two equal reads demonstrate **present stability**, not historical identity. Avoid claiming live qualification based on offline simulation or generic CI success alone.
