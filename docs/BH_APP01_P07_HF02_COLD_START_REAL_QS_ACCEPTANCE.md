# BH-APP01 P07 HF02 — API36 QS confirmation cold-start acceptance

## Exact-HEAD evidence

`43653310203` (PR) and `43653305150` (push), SHA `e9226b1d671cdcf351c33fc7eee770d6a8a2565a`, each failed only in `P07HostedUiTest.updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled` at AndroidX ActivityScenario.launch(custom Intent) state `PRE_ON_CREATE`. Both ran three tests; the other two passed. Source and Android compilation succeeded. The downloaded HF01 failure artifact contains a launcher-screen screenshot, an AndroidJUnit XML with exactly one failing test and no application exception trace in the bounded logcat.

This does **not** prove that the Android app fails when launched with the QS intent. The previous HF01 modal deferral remained inconclusive. Do not work around the test by removing QS confirmation coverage, skipping it or claiming hosted qualification from source tests.

## Consolidated fix

1. Instrumentation still checks **real Android ActivityManager onNewIntent** after `ActivityScenario.launch(MainActivity.class)` successfully reaches RESUMED: uses `activity.startActivity(qs)` with explicit SINGLE_TOP/CLEAR_TOP, observes the actual native confirmation dialog, taps **Cancel**, and asserts the app stays open and the one-shot intent is consumed. This avoids the API36 AndroidX custom-intent launch behavior associated with repeated PRE_ON_CREATE timeouts.
2. **Independent cold start:** The hosted-only script force-stops the disposable emulator companion, calls `adb shell am start -W -n ... -a com.mikeyphw.bindhosts.CONFIRM_UPDATE`, strictly checks `Status: ok`, polls an actual UIAutomator XML tree for the confirmation title and exactly one enabled/clickable Cancel button, screenshots that dialog, taps the Cancel button at validated bounds, and reads three native fixed-tag log events for accepted intent, shown dialog, and Cancel. No positive Update action is ever clicked.
3. The signed-off evidence includes the three passing AndroidJUnit tests and **separate** cold-start receipt, emulator hierarchy, screenshot and log. The verifier refuses absent/mismatched SHA, missing/false cold-start receipt, failed/errored/skipped tests, missing Cancel proof, missing screenshot, or any failed-command marker.
4. The exact-SHA PR, required four workflows, local no-Gradle policy and physical Android16 no-write boundary remain unchanged. Hosted success is NOT signed release or physical-device acceptance. Source tests cannot prove this fix works on API36; GitHub must run the actual emulator.

## Failure diagnostics

The previous HF01 capture of emulator-only logcat, instrumentation XML and failure screenshot is preserved. HF02 additionally collects a UI hierarchy and bounded native intent/dialog/cancel event log so a future failure distinguishes AndroidX launch harness behavior from actual ActivityManager cold-start UI behavior.
