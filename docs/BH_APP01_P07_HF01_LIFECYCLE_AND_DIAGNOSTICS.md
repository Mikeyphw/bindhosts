# BH-APP01 P07 HF01 — Hosted Android16 confirmation lifecycle + diagnostics

## Reproduced hosted failure

Both P07 runs `43650952143` (PR) and `43650945179` (push) had **two successful tests of three**. `P07HostedUiTest.updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled` timed out at ActivityScenario state `PRE_ON_CREATE`. The APK, test APK, x86_64 emulator and API36 boot all completed. Existing `MainActivity.consumeUpdateIntent` opened `AlertDialog` synchronously while `onCreate` was still running.

## Scoped fix

- Clear `ACTION_CONFIRM_UPDATE` on receipt (one-shot), store a pending flag, then post to the Activity UI queue only after resumed; avoid nested/duplicated dialog dispatch and dismiss a live confirmation when destroyed.
- Preserve the real cold-start ActivityScenario intent-based test and the explicit Cancel test. No positive Update tap or system hosts write is performed.
- Add regression tests for `onResume`/`onPause` gating and source-level no-immediate-dialog behavior.
- Always preserve failing emulator test reports, bounded emulator-only AndroidRuntime/ActivityManager logcat and a separate *failure* screenshot. The instrumentation return code remains nonzero, and the `bh_app01_p07_signoff.py` verifier continues to refuse any missing, failed, skipped or incorrect-SHA evidence.

## Qualification boundaries

This only fixes the observed hosted UI test infrastructure/lifecycle race. It does not claim hosted CI passes before a new actual run, does not authorize physical Android16 installation/root/device writes, and is not personal release qualification. The previous four required workflow policy remains unchanged.
