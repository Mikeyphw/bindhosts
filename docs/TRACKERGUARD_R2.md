# TrackerGuard R2 — opt-in package observer and receiver reconciliation

R2 adds a root-only, private, **opt-in** package monitor to bindhosts. It uses
polling every 120 seconds (and after reboot) instead of a permanent Android app
or broadcast listener. By default the monitor is **off**, the enrollment list
is **empty**, and installation alone does not change any IFW rules.

Only user-installed packages may be enrolled. `enroll PKG` is an explicit
permission to add automatically selected receiver blocks **immediately** for
that package, even if periodic monitoring is disabled. Once the monitor is
enabled, it tracks package version/source changes, reconciles signed receiver
classes on updates, removes R2-owned rules on uninstall, and restores them on
reinstallation. The package scan is derived from the installed base APK's
binary manifest, not manifest strings in dex files or split APK manifests.

## CLI

```sh
su -c 'bindhosts tracker status'
su -c 'bindhosts tracker preview com.example.userapp'   # read-only
su -c 'bindhosts tracker monitor status'
su -c 'bindhosts tracker monitor once'                   # one snapshot
su -c 'bindhosts tracker monitor enable'                 # opt in to 120s polling
su -c 'bindhosts tracker enroll com.example.userapp'     # opt in to auto block
su -c 'bindhosts tracker exclude com.example.userapp'    # keep manual rules
su -c 'bindhosts tracker include com.example.userapp'
su -c 'bindhosts tracker unenroll com.example.userapp'   # undo only auto rules
su -c 'bindhosts tracker monitor disable'                # preserve blocks
su -c 'bindhosts tracker json status'
su -c 'bindhosts tracker json rules'
```

`monitor disable` stops observation but intentionally **does not** lift IFW
rules already installed. Use `unenroll PKG`, `exclude PKG`, or `restore PKG`
for block removal. An explicit manual `add` or R1 batch `block PKG` promotes
existing matching auto-owned rules to manual so a later `unenroll` does not
silently remove your deliberate blocks. `restore --all` still removes all
TrackerGuard rules and clears enrollment, but never touches other tools' IFW
files, including App Manager's.

## Safety boundaries

* **Automated receiver rules only.** Android 16/KSU device acceptance tested
  broadcast receiver blocking and rollback; services and activities need
  separate end-to-end verification and are manual-only in this release.
* **Curated signatures only** (`review` entries in shipped signature database),
  and only for manifest components explicitly enabled in `base.apk`.
* Existing manual IFW rules and other managers' XML files are preserved.
* Scanner/package-manager failures retain prior rules and avoid treating a
  malformed or empty package list as a mass uninstall.
* State in `/data/adb/bindhosts/trackerguard` remains root-only (mode 0700,
  metadata mode 0600); `monitor.log` is capped after rotation.
* Polling is neither immediate nor guaranteed at every moment. Reboot, power
  management, package database delays and root process lifecycle may delay a
  scan; `monitor once` provides explicit reconciliation.
* On a rare crash between IFW/rule-list commit and auto-ownership commit,
  affected rules can conservatively remain blocked as manual until explicit
  `restore` or `remove`. This is safer than silently unblocking them.

## Runtime acceptance

Run `sh tests/trackerguard-r2/run-device-acceptance.sh` on Termux after
installing the CI-built R2 ZIP. Initial verification is read-only regarding
IFW rules and asserts the previously retained AppsFlyer rule is unchanged.
Then opt in to monitor and enroll a **nonessential** user app after inspecting
`tracker preview PACKAGE`. Use `tracker json rules` to observe ownership.
The R0/R1 Android IFW lab in PR #4 has already established live receiver
blocking. R2 update/uninstall polling requires a follow-up install/update test
using the lab APK or another controlled app.

## Data files

* `enrolled.tsv` — packages individually opted in for R2 auto receiver rules
* `excluded.tsv` — packages explicitly excluded from auto rules
* `auto.tsv` — ownership metadata for R2-added rules only
* `seen.tsv` — Android package-manager snapshot
* `monitor.enabled` — explicit monitoring opt-in marker
* `watch.pid` — watcher PID, `monitor.log` — status and observation log

## Build

CI builds the existing bindhosts WebUI and all supported native ABIs. R2
regression tests exercise enrollment/exclusion, manual/auto separation,
package version changes, uninstall/reinstall, scanner failures, malformed
snapshots, JSON status, and restoration. Qualified releases remain gated by
manual release workflow; passing host CI is not an automatic release.
