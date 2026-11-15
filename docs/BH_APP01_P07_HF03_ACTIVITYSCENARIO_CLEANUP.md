# BH-APP01 P07 HF03 — ActivityScenario cleanup regression repair

## Evidence and exact source pin

PR #19, repository `Mikeyphw/bindhosts`, source `cc5293d02e1cbc09b39368dcae1e47c709bf3284`.
The push run `43662821619` and PR run `43662825585` both reached the disposable API36 emulator and built the app and instrumentation APK. All source, WebUI and TrackerGuard workflows passed. The emulator ran all three instrumented tests: UX10 bundle load and bridge security checks passed, while `updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled` failed during **try-with-resources cleanup**, after its dialog and Cancel assertions completed.

The downloaded failing JUnit report (`TEST-emulator-5554 - 16-_app-.xml`) specifies:

```
java.lang.AssertionError: Activity never becomes requested state "[DESTROYED]" (last lifecycle transition = "PAUSED")
at androidx.test.core.app.ActivityScenario.close(ActivityScenario.java:421)
at com.mikeyphw.bindhosts.P07HostedUiTest.updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled(P07HostedUiTest.java:122)
```

This is a different error from HF01's `PRE_ON_CREATE` timeout. HF02's action `activity.startActivity(qs)` inside `scenario.onActivity` created a competing ActivityManager transition, leaving the ActivityScenario lifecycle `PAUSED` during auto-close. The exact transition responsible remains an inference; the cleanup location and PAUSED state are directly confirmed by the XML. This overlay prevents that particular competing transition.

## Narrow implementation

- Keep the real hosted instrumentation test name and every assertion: launch main Activity through ActivityScenario, deliver the QS intent directly to `MainActivity.onNewIntent` on that same UI-thread Activity instance, verify the native confirmation, tap **Cancel**, verify intent consumed and Activity remains not finishing, then explicitly assert `RESUMED` before automatic cleanup.
- **No acceptance gate removed:** the independent GitHub-only `bh_app01_p07_emulator.sh` still force-stops and performs a **real** `adb shell am start -W -a com.mikeyphw.bindhosts.CONFIRM_UPDATE`. It requires a real UIAutomator hierarchy containing an enabled Cancel button, screenshots the confirmation dialog, taps only Cancel, and requires exact native intent/dialog/cancel event receipts. The evidence verifier requires all three passing AndroidJUnit cases **plus** the independent real-cold-start proof.
- No changes to native app runtime, hosts write backends, production WebUI, source catalog, or TrackerGuard. No local Gradle or physical-device writes.

The new source unit test explicitly refuses the previous startActivity-under-ActivityScenario regression. The actual hosted API36 result is pending until this overlay is pushed and all four exact-SHA workflows pass. Physical Android16 acceptance and release signing are separate gates.
