# bindhosts + TrackerGuard implementation and acceptance audit — R3 HF01

## Evidence and scope

Source review: `Mikeyphw/bindhosts`, with UX06 PR #10 head pinned to
`2b28f140c817491cfa5dd312139765bbebf767af`. Historical PR status and
GitHub Actions successful runs were checked before this overlay was prepared.
The R3 HF01 overlay must be tested on hosted CI after application. Passing
simulated tests is not device runtime qualification.

| Milestone | Implemented at source | Known acceptance gap |
| --- | --- | --- |
| TrackerGuard R0 | Dedicated IFW XML, exact manual component rules, add/remove, app-scoped and all-rule restore | Live IFW lab reports receiver enforcement; services/activities not individually qualified |
| TrackerGuard R1 | Binary manifest scanner, curated exact-prefix signatures, read-only preview, opt-in batch actions, native CI scanners | Base APK only; split manifests/DEX and nonmanifest SDK trackers not detected |
| TrackerGuard R2 | Opt-in package monitor, enrolled/excluded state, receiver-only ownership and reconciliation, manual-rule preservation | Physical-device install/update/uninstall/reinstall lifecycle needs R3 acceptance |
| UX01 | Five-tab WebUI, curated opt-in sources, Apps and Rules, AMOLED preference | Manual device visual and external feed URL/availability checks outstanding |
| UX02 | Validated source updates, HTTPS source requirement, fail-closed downloads, root editor API | On-device network/TLS variability and live source error receipt inspection outstanding |
| UX03 | Journaled hosts writer, safer reset/toggle, ownership display, pre-mount recovery hotfixed here | Mode 2 atomic round-trip verified by user on Android 16; real bind-mount in-place fallback and overlay modes not fully qualified |
| UX04 | Loopback-only HTTP GIF/SVG responder, opt-in off by default, HTTPS explicitly unsupported | Physical-device localhost port 80, SELinux and WebUI interaction checks outstanding |
| UX05 | Private bounded redacted receipts, Activity screen, diagnostics export | On-device navigation, export, and persistence checks outstanding |
| UX06 | Private checksummed snapshots, preview/import/export, recovery journal, source health, hosted CI | PR #10 is open at audit time; real device backup/restore and crash recovery tests outstanding |
| TrackerGuard R3 | Isolated v1/v2 APK lifecycle harness, test-only signature, offline mock tests and hosted Gradle build definitions | R3 PR/hosted build and explicit live device lifecycle acceptance pending |

## Concrete hotfixes folded into R3 HF01

1. **Pre-update observer baseline:** The R3 harness now seeds R2's `seen.tsv`
   with the v1 lab package before testing that v2 triggers an update event.
   R2 intentionally suppresses events on its first snapshot; the old test
   would otherwise fail even on a correctly functioning device.
2. **Enforcement checks:** After updating v1 to v2, the test verifies the
   receiver remains denied; after unenrollment, it verifies delivery resumes.
   This checks Android enforcement, not merely XML/rules entries.
3. **Post-run observer state:** The test verifies no isolated lab package
   entry remains in the final R2 `seen.tsv`. It does not erase legitimate,
   root-private `monitor.log` history or claim byte-for-byte restoration of
   unrelated package-manager observation snapshots.
4. **Boot recovery ordering:** `service.sh` attempts a pending hosts-journal
   recovery before bind/redirect modes activate their mount. If recovery
   fails, it refuses to continue. Modes 7/8 are overlay mounts and require
   mounting their overlay first, so there remains a brief risk of exposure
   before the post-mount recovery; power-loss atomicity is not guaranteed.
5. **First-boot file path:** `post-fs-data.sh` no longer appends to an ambient
   `$MODPATH/system/etc/hosts` when creating a missing managed hosts file.
   It stages next to the module's `$MODDIR` target for atomic rename, rejects symlinks, and refuses initial-copy errors.
6. **Local+hosted regressions:** R3 mock lifecycle tests, boot recovery tests,
   `sh -n` and the existing UX02–UX06 tests are included in the installer/CI.

## Explicit non-goals

No new default tracker blocking, no automatic services/activities protection,
no HTTPS interception, no hidden network calls, no automatic release, and no
automatic R3 merge. Termux does not compile the Android app or native scanners.

## Remaining gate sequence

1. Apply the consolidated overlay. It first guards and merges UX06 PR #10 if
   still open; then source-pins, validates, commits/pushes R3, creates a PR,
   and watches module and lab APK hosted workflows at the exact commit.
2. Install **the hosted CI module**, reboot and inspect runtime status.
3. Use `tests/trackerguard-r3/run_device_acceptance.py --read-only` before
   choosing to run the explicit v1/v2 device lifecycle test.
4. Verify UX05 Activity and UX06 backup preview/restore on the device; the
   HTTP responder requires its own explicit opt-in acceptance if desired.
5. Merge R3 only after its hosted and targeted device checks pass.
