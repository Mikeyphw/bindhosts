# BH-APP01 P07 PH03 — Android 16 ARM64 UI/SAF/QS journey acceptance

**Source parent:** `09ac4a9b94bd0df6fb2446a41c974d3ddb1a68c6` · PR #19. All four hosted PR workflows at this parent were green. The PH03 commit must pass the same four workflows at its **new exact HEAD** before any device testing.

## Scope and authorization

`bh_app01_p07_ph03.py` inherits PH02's independent live GitHub PR/workflow/artifact validation and PH01's installed-APK SHA-256 matching requirement. No install, root request, hosts updates, TrackerGuard IFW changes, Android setting changes, screenshot storage, document selection, or general shell command is allowed. Exactly one physical Android 16 ARM64 device at ADB serial `localhost:5555` is required. The suite's only Android writes are explicit UX actions (starting the app/Activity, tapping **navigation** and **Cancel**, pressing Back), and a temporary uniquely named UIAutomator hierarchy file that is deleted and checked for absence. A failed cleanup fails the entire run.

**No device actions happen by applying or publishing this overlay.** Default `--test` validates source and synthetic Git only.

After *new HEAD CI green*, obtain exact new hosted artifact (and exact debug APK) using:

```zsh
cd "$HOME/Code/bindhosts"
SHA=$(git rev-parse HEAD)
python3 scripts/ci/bh_app01_p07_ph03.py hosted --source-sha "$SHA"
```

To inspect the physical device, explicitly authorize read-only ADB queries:

```zsh
python3 scripts/ci/bh_app01_p07_ph03.py preflight --source-sha "$SHA" \
  --serial localhost:5555 --ack I_AUTHORIZE_READ_ONLY_DEVICE_PROBE
```

The installed APK must be **byte-identical** to the hosted API36 test APK for this HEAD. PH03 never installs it. If an old or absent APK is detected, do not force past the refusal; installation requires separate deliberate authorization.

Then, with consent to UI interaction:

```zsh
python3 scripts/ci/bh_app01_p07_ph03.py navigation --source-sha "$SHA" \
  --serial localhost:5555 --ack I_AUTHORIZE_PH03_NONROOT_UI_ACTIONS
python3 scripts/ci/bh_app01_p07_ph03.py saf-cancel --source-sha "$SHA" \
  --serial localhost:5555 --ack I_AUTHORIZE_PH03_NONROOT_UI_ACTIONS
python3 scripts/ci/bh_app01_p07_ph03.py qs-duplicate-cancel --source-sha "$SHA" \
  --serial localhost:5555 --ack I_AUTHORIZE_PH03_NONROOT_UI_ACTIONS
```

`all` combines the three interactive journeys. **SAF requires the user to open the real Android picker manually from the app while the script observes. Do not choose a private file.** The suite cancels the picker and confirms the app resumes, but does not claim a successful actual-file import. QS sends two fixed confirmation intents, observes the native dialog, taps only its verified Cancel button, and checks it does not reappear. Navigation permits only strictly matched footer-tab text in the bottom screen region, with page-specific content markers. If accessibility trees are missing/ambiguous, the result is `REFUSED`/inconclusive, not a fabricated pass. The user can inspect a private JSON receipt under `~/.local/state/bh-app01/p07-ph03`; raw UI hierarchy and private content are not stored.

Full physical acceptance remains **false**, because module update/restore, IFW preservation, signed APK and release checks are still separate milestones. PH03 verifies only limited non-root UX journeys. All Gradle compilation stays on GitHub Actions. No force-push or automatic merge.
