# UX09E — physical WebUI acceptance and evidence gate

Base: `Mikeyphw/bindhosts` UX09 PR #15 at `f32076e87164499ad693f9365c30a622e0fcc832`.

This phase adds a **real device acceptance runner**, not a simulation of Android UI tests and not a claim that PR #15 is physically qualified. Runs in Termux using local ADB for API 36 arm64-v8a; no Gradle on the phone. Existing hosts and TrackerGuard/IFW code are unchanged. Hosted Actions runs only **offline mock/negative tests** of this runner.

## Preflight contract

`python3 tests/ux09e_device_acceptance.py probe --serial localhost:5555`

Read-only checks: ADB device, Android API and ABI, root uid, exact SHA-256 of UX09's two new root scripts, `--hosts-control status`, UX09 operation `status` and `events`, applied-vs-configured fingerprint status, and hashes of 5 private configuration files. Reports source digests as pass/refuse only, never installed packages, rule domains, URLs, raw logs or host entries. No temp file or IFW modifications on device.

If the correct UX09 module is missing, it **refuses**. The GitHub Actions artifact from successful run `43545095843` on the exact UX09 commit is available separately; installing it requires explicit human authorization, and a reboot is a separate manual action. Source-only overlay `apply` does not install a module.

## Opt-in physical walk

`python3 tests/ux09e_device_acceptance.py walk --serial localhost:5555 --ack I_AUTHORIZE_UX09_MANUAL_UI_ACCEPTANCE`

This performs no automated UI tapping. A human opens bindhosts WebUI, looks at Sources/Rules/More, confirms each step, and gets a private local JSON report. Manual claims are labeled MANUAL_UI_OBSERVED, not automated instrumentation.

Additional flags are independent and explicitly authorized by a second typed phrase:

- `--test-toggle`: tap Pause then Resume (or reverse if initially paused), verify each state through the backend and restore initial state.
- `--test-source`: save one alternate preset; require the source file hash to change and `BH_UX09_APPLIED=PENDING`; restore original selection; refuse unless **all** recorded configuration fingerprints match the initial bytes. No silent rollback or replacement of user rules.
- `--test-update`: only when blocking is ACTIVE or INACTIVE. Require `UPDATE_REAL_HOSTS` typed and the user to tap **Update hosts**. Verify backend state DONE, measured STATS data, applied status CURRENT, and no configuration mutation. The existing journaled hosts pipeline handles the actual modification; the harness does not run updates or write hosts itself. A network error is a failure, not a success claim.
- `--capture`: optionally take local PNG screenshots of what is currently on screen; not required and may contain private app information. Not uploaded. Never read screenshots using OCR to claim UI success.

All written JSON reports are local, default `~/.local/share/bindhosts-ux09e`, mode 0600. No `screenshots` unless explicitly requested. A failed manual check or a mismatched state *refuses* and does not perform automatic rollback or a retry.

## Acceptance matrix

| Gate | Source of evidence | Pass criterion |
|---|---|---|
| Exact installed UX09 module | Root SHA-256 of two fixed scripts | Both match pinned source |
| Backend available | `--hosts-control status` and operation status | Known enumerated states |
| Sources/Rules/More | Human-visible WebUI check | Explicit manual confirmations |
| Pause/Resume | Human tap + backend read-back | Changed state then restored baseline |
| Preset selection | Human save + file SHA-256 + backend | Source hash changed, PENDING, original bytes restored |
| Update terminal | Human observation + operation journal | DONE, measured stats, CURRENT, sources unchanged |
| Report privacy | Offline tests | No raw hosts, URLs, IFW, package names or device stderr |
| Hosted runner contract | Both workflows | Offline negative tests pass |

## Release gate

No PR merge, module install, device mutation, SELinux change, trust certificate import, IFW test, or reboot is triggered by `apply`, `verify`, `self-test`, or `ci`. Physical Android acceptance must be performed **after** the appropriate UX09 module has been explicitly installed and rebooted. This phase does not qualify TrackerGuard R3; that remains a separate gate.
