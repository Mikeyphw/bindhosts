# TrackerGuard R3 HF04 — PackageManager root transport hardening

## Observed condition

The Android 16 device passed the R3 read-only preflight, the isolated lab app's baseline receiver delivery, and the cleanup verifier; however the initial R2 monitor snapshot refused after **both root `pm` and `cmd package` queries returned nonzero**. The HF03 snapshot syntax parser is not responsible for command return codes. Prior root diagnostics were successful while the test APK was absent. A transient PackageManager failure, root shell/PTY I/O, or SELinux/Binder issue remains to be distinguished by read-only evidence.

## Fix scope

- A dedicated helper queries `/system/bin/pm` by default and `/system/bin/cmd` as fallback. Both use `</dev/null` and capture output/error in private root storage, not a Termux PTY.
- Three bounded read-only query attempts (1 second, then 2 seconds between failures). Return success only for nonempty successful commands, then use **the existing strict HF03 parser**. No automatic enrollment, IFW writes, rule restoration, policy changes, or live device test is performed by the overlay.
- On permanent failure preserve prior `seen.tsv`, rule state and IFW; report exit codes, known error classes and stderr byte counts **without leaking packages, stderr, or stack traces**.
- HF02/HF03 parser tests are retained and updated for the helper. Nine additional POSIX tests cover success, fallback, transient and permanent failures, empty output, Symlink/unsafe targets, rollback, and redacted errors.

## Order of operations

1. Run the ZIP's `diagnose` (read-only PackageManager context comparison and private rule hash stability).
2. Run `self-test` and `audit` against the exact UX08 source SHA.
3. Run `apply` to create a **new stacked PR** on top of UX08 #13. Source pins and changed-file inventory must match; the launcher never merges branches, modifies the phone or installs modules.
4. Wait for **both** hosted checks on the exact new SHA; then download/verify its module artifact and install via KernelSU only after further confirmation.
5. Reboot and rerun the separately authorized isolated R3 lifecycle test. Original IFW rule hashes should be independently compared when an original pre-test baseline exists.

Even if this workaround passes host CI, **the specific Android 16 failure is not qualified** until an on-device run reaches `TG_R3_LIVE_ACCEPTANCE_PASS` and cleanup. Do not disable SELinux or add broad allow rules as a workaround.
