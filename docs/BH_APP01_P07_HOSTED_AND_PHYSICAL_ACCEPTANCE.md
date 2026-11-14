# BH-APP01 P07 — API36 emulator and read-only Android16 preflight

Source branch: `feature/bh-app01-p00-p03-companion-foundation-20261114`, PR #19.

## Hosted integration (new required workflow)

`bh-app01-p07-api36.yml` is a **required** fourth workflow. It explicitly checks out the PR's **head SHA** rather than the synthetic merge SHA. It builds the actual UX10 companion assets, boots one disposable API36/x86_64 Google APIs emulator and runs AndroidJUnit4/Espresso instrumentation tests, without writing to a physical device.

- Real Activity and offline UX10 WebView asset mount, plus file/content access restrictions.
- Manifest network-permission refusal and typed native command rejection.
- Update QS tile confirmation opened, **Cancel** tapped; no update/root mutation triggered.
- Android test XML, screenshot and debug APK SHA as evidence.
- Fail-closed `p07_signoff.py`: missing, skipped or failed journeys, mismatched SHA, absent screenshot or APK receipt cannot qualify the hosted test.
- Success produces `hosted-receipt.json`, with `hosted_api36_qualified=true`, `physical_android16_qualified=false` and `release_qualified=false`.

The existing Foundation, WebUI and TrackerGuard workflows remain mandatory, with strict Gradle Lint still enabled. No test bypass or release signing is introduced.

## Physical Android 16 (inspection only)

Termux read-only inspection, explicitly gated:

```zsh
python3 scripts/ci/bh_app01_p07_physical_probe.py \
  --serial localhost:5555 \
  --ack I_AUTHORIZE_READ_ONLY_DEVICE_PROBE \
  --output "$HOME/.local/state/bh-app01/p07-physical-readonly.json"
```

This reads API/ABI, installed package and Quick Settings services using **ADB queries only**. It never installs, launches, grants root, mutates settings, touches hosts/IFW, or claims physical acceptance. App absence is reported as not installed, not as a successful device test.

**Still required for physical acceptance**: user-approved APK installation, real UI navigation/rotation/keyboard and SAF cancellation/import; QS toggle pause/resume read-back, update confirmation/race handling, existing hosts backup/restore proof, TrackerGuard IFW ownership/restoration, root denial, diagnostics and receipt checks. Keep this separate from emulator green and from any personal release/signing qualification.

**Additional remaining roadmap**: P07 device acceptance and negative restoration, P08 personal signing/provenance/rollback, P09 parity drift and compatibility checks. No automatic releases.
