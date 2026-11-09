# TrackerGuard — controlled Android 16 IFW qualification lab

The lab APK is deliberately separate from the bindhosts systemless-hosts module.
It contains one `exported` test receiver with a declared action and a simple Activity
(to clear the app's initial stopped state). It has **no INTERNET permission**, no
analytics SDK, no persistence service, and is debuggable for `run-as` inspection.

## Build

GitHub Actions workflow: `.github/workflows/trackerguard-ifw-lab.yml`.
Requires JDK 17, Gradle 8.13, AGP 8.13.2, API 36. The workflow packages
`trackerguard-ifw-lab-debug`, containing `app-debug.apk`.

## Termux device qualification

With ADB already configured as `localhost:5555`, download the APK to
`/sdcard/Download/TrackerGuard-IFW-Lab/app-debug.apk` and run:

```sh
sh ~/Code/bindhosts/tests/ifw-lab/run-device-test.sh \
  /sdcard/Download/TrackerGuard-IFW-Lab/app-debug.apk
```

Override the transport with `ADB_SERIAL=...` if needed. The sender is **adb shell
(uid 2000)**, not KernelSU root. The evidence is the receiver's own private
`files/received-events.log`, read via `run-as` (debug app only), not merely the
`am broadcast` result or an IFW log-count message.

The harness executes three comparisons:
1. Before block: receiver records nonce #1.
2. While `bindhosts tracker add` owns exactly the lab receiver: nonce #2 does
   not appear in the app's private log.
3. After `bindhosts tracker remove`: receiver records nonce #3.

It refuses a pre-existing lab rule, keeps all other TrackerGuard rules, and
installs a cleanup trap to remove its own newly-created lab rule on failure.
If the harness reports no baseline delivery or absent receiver records,
no IFW enforcement claim is made. A negative observation is meaningful only
when baseline and restored positive controls both succeed.

The app remains installed for repeatable testing. Uninstall only when finished:
`adb -s localhost:5555 uninstall com.mikeyphw.trackerguard.ifwlab`.

This test validates broadcast IFW for a controlled exported receiver. It does
not by itself establish that all tracker SDKs, their network requests,
services, or content providers are blocked on Android 16.
