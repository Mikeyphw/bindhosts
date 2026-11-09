# bindhosts UX03 + UX04 — unified acceptance and delivery

Source baseline: `311b03ffb4977b523ae8ff45f3c51b4203c51c15` (`master`, after UX01 PR #6 and UX02 PR #7). Target module version `v2.1.5-tg.0.7` (`21607`). No automatic release or installation.

## UX03: safe hosts writes, reset and application controls

- `hosts_target_safe.sh` is the **single journaled commit path** used by hosts updates, manual reset/quick toggle, and instant allowlist edits. It attempts a verified same-directory atomic rename on normal files, then falls back to verified in-place writes if a bind mount refuses rename. A journal with the exact previous bytes is persisted before touching the active target. A failed write is rolled back when possible; incomplete transactions refuse further commits until recovery.
- `service.sh` checks a persistent journal at boot and tries to recover it before starting the optional response server. If recovery fails, it preserves the journal and writes a diagnostic instead of deleting evidence.
- `hosts_reset_safe.sh` stages a complete reset candidate before writing. Quick toggle preserves a backup for restoration; disabled custom hosts entries stay disabled.
- `module/hosts_mount_acceptance.sh` supports read-only inspection by default and an explicitly requested live marker-write/restore check. It uses the device's active hosts mode and does not remove TrackerGuard IFW rules. The live check temporarily changes the active hosts file, so it is **opt-in and not a substitute for a complete mounted-device test**.
- The Apps WebUI gains one-shot R2 reconciliation, explicit refresh, and read-only per-rule ownership (manual vs R2 automatic). It **does not** enroll apps, enable polling, or expand automatic blocking without explicit confirmation.

## UX04: optional local HTTP blocked-image response

- New tiny C HTTP responder, built with the Android NDK for arm64-v8a, armeabi-v7a and x86_64 in hosted GitHub Actions. It binds **127.0.0.1 only**, has no outbound requests, reads at most 2047 request bytes, responds to GET/HEAD, and never collects request logs.
- Modes: **off** (default), **transparent GIF** (1×1), or built-in **bindhosts blocked SVG image**. Fixed assets are compiled into the native server; no runtime arbitrary HTML, script evaluation, or TLS interception.
- Users choose the mode in **Sources → Blocked-page image**, with a confirmation dialog. `bindhosts --response status|set off|set transparent|set logo` is also available. The startup service restarts it only if the saved mode is enabled.
- **HTTP only.** HTTPS, certificate pinning, HSTS, and ad containers in pages are not intercepted. A loopback image does **not** mean every ad will show a visible picture.
- First run requires a regular **Update hosts** from UX03 to create `# bindhosts-custom-start/end` and `# bindhosts-block-start/end` markers. This preserves user-defined custom mappings when converting only blocked entries from 0.0.0.0 to localhost.
- When off, only previously tagged `# bh-response` entries revert; manual `127.0.0.1` mappings remain unchanged. If the server cannot bind port 80, the mode switch fails without switching the hosts mappings.

## Local and hosted tests

- `python3 tests/test_hosts_target_ux03.py` — journaling, failpoints, bind-mount fallback simulation, reset/toggle and recovery
- `python3 tests/test_blocked_response_ux04.py` — host-compiled C loopback responder, mode changes, rollback and content types
- `python3 tests/test_webui_ux0304.py` — guarded UI and boot integration
- Existing UX01/UX02, R0/R1/R2 tests remain in hosted CI.
- CI builds native Android server per supported ABI, builds Vite WebUI, and packages a KernelSU module ZIP. Termux **does not build Android binaries**.

## Rooted device acceptance after hosted CI and installing the module

Read-only (no modification):

```sh
su -c 'sh /data/adb/modules/bindhosts/hosts_mount_acceptance.sh --read-only'
su -c 'sh /data/adb/modules/bindhosts/bindhosts.sh --response status'
su -c 'sh /data/adb/modules/bindhosts/bindhosts.sh tracker json status'
```

Optional live round-trip (temporarily changes the actual hosts file and immediately restores its original bytes):

```sh
su -c 'sh /data/adb/modules/bindhosts/hosts_mount_acceptance.sh --probe-live --accept-risk'
```

If live acceptance fails, retain logs and the journal directory under `/data/adb/bindhosts/`. Do not remove a pending journal. The verified in-place fallback can still expose a short partial file if power is lost; boot-time recovery improves resilience but cannot guarantee atomicity on mounts that refuse rename.

## HF01 audit corrections (consolidated into this overlay)

- Fixed the read-only acceptance path: `inspect` no longer creates a lock directory. Unknown acceptance flags are refused rather than accepted as read-only.
- The installer now executes the native responder's C-loopback and integration tests during local validation, not just in hosted CI.
- Switching the image style now restarts a missing responder when the selected mode is re-applied. If the daemon fails to start at boot, the control script attempts to revert managed hosts mappings to normal `0.0.0.0` blocking and save `off`. A failed hosts write is reported, not hidden.
- Turning image mode `off` works after an explicit reset removed the managed block-section markers, provided no tagged response mappings remain.
- Corrected native HTTP server signal handling so `SIGTERM` interrupts the blocking socket accept call, and reduced wait time for stopped/zombie processes.
- During uninstall, a pending journal is recovered first. If recovery cannot succeed, persistent state containing the only previous-hosts snapshot is preserved for manual recovery, rather than deleted.
- A prior successfully committed UX03/UX04 feature branch is checked against the exact HF01 expected file bytes. A confirmed old branch receives a normal hotfix commit, never a force-push or silent skip.

**Still unqualified:** actual Android 16/KernelSU mounted-hosts round trip, SELinux/service startup and Android NDK/hosted WebUI builds. Local simulation does not substitute for those tests. The `0.0.0.0` fallback is not power-loss atomic.
