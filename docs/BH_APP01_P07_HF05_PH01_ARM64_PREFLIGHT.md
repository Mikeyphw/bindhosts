# BH-APP01 P07 PH01 — source-pinned ARM64 read-only preflight

This consolidated overlay **includes HF05**; apply it once to the same verified PR #19 parent `da7fa5b9bf67353eff6f4c4307e63a272c3bbd32`. It does not require applying the previous HF05 archive first.

## Scope

- **HF05**: hosted API36 test APK reinstallation after AndroidJUnit teardown, exact built-to-installed APK digest check, real QS dialog/cancel verification, no physical installation.
- **PH01**: enhanced read-only physical Android 16 ARM64 preflight, exact hosted receipt source pin, installed APK SHA-256, QS component declarations, SELinux readback and root-manager package detection. The tool never requests root or performs Android writes.
- Host-only adversarial tests cover mismatched source/ABI/API/installed APK, rejected commands, forged hosted claims, invalid serial, oversized ADB output and private report storage. The read-only gate always sets `physical_android16_qualified=false` and `release_qualified=false`.

## Apply (Termux / Zsh)

```zsh
python3 /sdcard/Download/BH_APP01_P07_HF05_PH01_ARM64_PREFLIGHT_CONSOLIDATED.zip --test
python3 /sdcard/Download/BH_APP01_P07_HF05_PH01_ARM64_PREFLIGHT_CONSOLIDATED.zip --apply --publish --root "$HOME/Code/bindhosts"
# Only if local commit exists or CI monitoring interrupted:
python3 /sdcard/Download/BH_APP01_P07_HF05_PH01_ARM64_PREFLIGHT_CONSOLIDATED.zip --resume --root "$HOME/Code/bindhosts"
```

## Later: physical read-only probe (never a release signoff)

Run this from the repository root, after obtaining the *new* hosted `hosted-receipt.json` from the **same exact commit** after all required workflows pass. On Termux:

```zsh
cd "$HOME/Code/bindhosts"
python3 scripts/ci/bh_app01_p07_physical_v2.py \
  --serial localhost:5555 \
  --source-sha "$(git rev-parse HEAD)" \
  --ack I_AUTHORIZE_READ_ONLY_DEVICE_PROBE \
  --hosted-receipt /sdcard/Download/hosted-receipt.json \
  --output "$HOME/.local/state/bh-app01/p07-arm64-readonly.json"
```

`--hosted-receipt` is optional, but omitting it cannot mark APK identity matched. A locally supplied receipt is **not independently verified** against GitHub. This script only prepares physical acceptance; no APK install, root change, hosts edits, IFW writes or screenshot capture. If the APK isn't installed, it records `INCONCLUSIVE` rather than claiming qualification.

Physical UI/SAF journeys, on-device hosts byte-level restoration, QS races and TrackerGuard foreign-IFW preservation remain **blocked until separate explicit approval**, with installation/rollback provenance checked first. P08 signing and P09 drift still pending.
