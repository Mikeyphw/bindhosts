# TrackerGuard R1 — AndroidManifest inventory and explicit batch blocking

Upstream bindhosts: https://github.com/bindhosts/bindhosts (WTFPL-2.0).
Fork branch base: `daf39325eafcb4e7970db3d14cc98cd99d517ede`, R0 on `Mikeyphw/bindhosts`.

## What's new

R1 adds a native `axmlscan` utility (MIT) built by GitHub Actions for Android arm64-v8a,
armeabi-v7a and x86_64. It reads **compiled binary AndroidManifest.xml** extracted
from the installed application's **base.apk**, without loading APK code or needing
Termux/Python on-device. It parses the declared manifest package and activity,
service, receiver, and provider names; disabled component flags are honored.

A curated, attributed signature subset is packaged in
`module/data/tracker-signatures.tsv`. These signatures are derived from
[MuntashirAkon/AppManager](https://github.com/MuntashirAkon/AppManager),
`app/src/main/res/values/trackers.xml` (GPL-3.0-or-later). The signature file
remains GPL-3.0-or-later; the independent AXML reader is MIT, and original
bindhosts files retain their upstream licensing.

## Commands (root via `su -c`, or existing bindhosts CLI)

```sh
bindhosts tracker scan com.example.app
bindhosts tracker preview com.example.app
bindhosts tracker block com.example.app
bindhosts tracker list
bindhosts tracker restore com.example.app
```

- `scan`: shows matching declared components (read-only).
- `preview`: labels which would be blocked (read-only).
- `block`: **requires an explicit app package**, writes eligible IFW rules in
  one batch using R0's ownership/rollback logic. Skips already disabled components.
- `restore`: removes only this module's own rules for the selected package.

If the manifest cannot be extracted or parsed, if its declared package doesn't
match the requested package, or if the signature file is invalid, no new rules
are written. Only user apps (`pm list packages -3`) are eligible. Content
providers are inventory-only: IFW cannot block providers.

## Important boundaries

- **No automatic install/update watcher in R1.** Opt-in automatic protection is R2.
- **No DEX scanning.** Only **manifest-declared** components in base.apk are
  discovered. SDK code with no declared component, or components declared only
  in split APK manifests, are outside the R1 scanner's coverage.
- Signature matching is a *candidate* signal, not proof that blocking a
  component is harmless. Use `preview`; blocking can break application features.
- IFW rules being written is not proof they are enforced on every Android build.
  Android 16 device-level enforcement and SELinux qualification remain pending.
- Do not install R1 from source without compiled native scanners. Download the
  **R1 CI module ZIP**, which includes the binaries and built bindhosts WebUI.
- The WebUI remains upstream bindhosts' implementation; a dedicated TrackerGuard
  page is planned for R3.
- Your Android version or kernel may require an appropriate mount mechanism for
  hosts-file redirection. This remains handled by bindhosts' existing modes.
- This fork's IFW file is `/data/system/ifw/bindhosts_trackerguard.xml` and
  its rule store is `/data/adb/bindhosts/trackerguard/rules.tsv`.
  It does not edit files created by App Manager or other IFW managers.

## Test coverage

`python3 tests/test_trackerguard_r1.py` compiles a Linux native scanner with
`cc`, generates synthetic Android binary manifests (UTF-8 and UTF-16), checks
malformed input rejection, tests manifest signature matching, rejects disabled
components, confirms preview is read-only, tests batch deduplication and
ensures failed scans leave persistent rules unchanged. Hosted CI builds the
actual Android binaries with the Android NDK and packages the complete module.

## PR and release safety

This R1 branch is based on the pushed R0 commit, but the recommended PR **targets
`master`**, including R0 and R1 atomically. Do not merge the separate R0 PR
first: its original release workflow can automatically publish an unqualified
R0 ZIP. R1 patches `.github/workflows/release.yml` to **manual qualified
workflow_dispatch only**, and ensures a future release builds all native
scanners and reruns R0/R1 tests. CI ZIP artifacts remain available for manual
laboratory testing before public release.
