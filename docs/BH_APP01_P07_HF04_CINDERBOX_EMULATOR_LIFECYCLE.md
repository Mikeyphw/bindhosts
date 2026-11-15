# BH-APP01 P07 HF04 — Emulator lifecycle and Cinderbox comparison

**Source pin:** `c8e3e6270f7eebfceb6760531e2cbc086614b2db` (PR #19). Failed hosted pull_request run `43664081823` and push run `43664078157` both at this SHA.

## Confirmed CI failure

The real hosted API36 emulator booted and completed Android compilation. The first two AndroidJUnit tests passed. The third test `updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled` verified the native confirmation and Cancel but failed on leaving its Java `try (ActivityScenario<MainActivity> ...)` block, when `ActivityScenario.close()` could not move the Activity to `DESTROYED` (last state `RESUMED`). The downloaded test report names `P07HostedUiTest.java:125`. HF02 earlier failed at the same cleanup site with last state `PAUSED`. Therefore changing `onNewIntent` alone cannot fix the test fixture's ownership/cleanup issue.

## Cinderbox cross-check

Inspected `Mikeyphw/Cinderbox-Companion` at SHA `2efb8b0ecd8408f31cecb28f986ab4c13c04f1d4`; successful hosted API36 journey run `43609355084`. It uses `ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d`, `ubuntu-24.04`, `google_apis` / `x86_64` / `pixel_6`, two cores and 3072M RAM / disk, with cameras disabled. HF04 ports the proven hosted runner pin/profile, **not** Cinderbox's Compose-specific tests or unrelated build structure.

## Fix and qualification rules

1. The QS *instrumentation* test now launches a real MainActivity via `Instrumentation.startActivitySync` (not `ActivityScenario`), invokes `onNewIntent` on the actual UI-thread Activity, verifies the real visible dialog, taps **Cancel**, asserts the Activity and WebView remain live, and calls `finish()` explicitly in `finally`. No `ActivityScenario.close()` path remains in this test. The original bundle-load test retains ActivityScenario and runs independently.
2. The separate `bh_app01_p07_emulator.sh` **real Android system cold start** remains untouched and mandatory: `am force-stop`, `am start -W -a ...CONFIRM_UPDATE`, UIAutomator dialog and enabled Cancel, screenshot, actual Cancel tap, and three native log events. Its independently SHA-bound verifier still requires all 3 real AndroidJUnit cases + this cold-start evidence.
3. Gradle runs on GitHub Actions only. No `continue-on-error`, no skipped UI tests, no auto-finish to mark tests green, no root writes or personal-device operations. This overlay does not qualify physical Android16 testing or release signing.

**Unverified until hosted execution:** whether the lower-level Android instrumentation fixture avoids all API36 lifecycle hangs and whether the independent ADB cold-start flow succeeds. If the hosted job still fails, inspect the XML and emulator evidence rather than altering acceptance criteria.
