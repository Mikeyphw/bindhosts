# Acceptance notes

The on-device `run-device-test.sh` is intentionally not part of GitHub-hosted
CI because it needs a user-owned, rooted Android 16 phone with working IFW.

CI checks the manifest and Java source contracts, shell syntax and mock ADB
behavior, then builds a debuggable APK. A mock can demonstrate rollback logic;
only the real device baseline/blocked/restored results qualify enforcement.

The test script's `TG_IFW_LAB_PASS` marker requires a positive baseline,
no receiver delivery while blocked, and a positive restored control. The
AppsFlyer rule from the earlier manual test is not changed.

`run-as` is available only because the test app is debuggable. The script
intentionally does not depend on `logcat` event semantics or the broadcast
command's completion code.
