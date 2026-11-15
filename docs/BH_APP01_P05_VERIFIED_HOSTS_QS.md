# BH-APP01 P05 — Verified hosts control and two Android Quick Settings tiles

## Implementation

**Source pin:** `6f8b17bdc7d07ce719acf45ce325bb656d7aadc2` (P04, PR #19).

The APK still builds the **same UX10 Vite entrypoint** as KernelSU WebUI, with the Android-only adapter substituting `kernelsu-alt`. New native operations are deliberately finite and available only for UX08/UX09 hosts operations. P05 does not grant arbitrary shell execution, source list writes, backup restoration, root module installation, or TrackerGuard mutations.

- The original `companion_api.sh` v1 (`hello`, `status`) remains unchanged.
- The new `companion_control_v2.sh` only accepts: `pause`, `resume`, `update-start`, `update-status`, `update-events`. It invokes original, journaled Bindhosts UX08/UX09 operations and rejects test override paths when executed as root. It never interpolates a path, domain, package, command, or URL supplied by the caller.
- `pause` and `resume` require matching pre-state, avoid running/interrupted updates, require the backend's success marker, and re-read the real hosts state. The UX08 backend retains backup/rollback and the shared hosts update lock.
- `update-start` only launches UX09's detached, journaled updater when safe and emits an accepted receipt after checking that execution is running or verified done; it **does not** treat launch as update success.
- `update-status` and `update-events` expose only a bounded, sanitized view of UX09's existing events, preserving pending/failure/interrupt distinctions. The events are base64-encoded to avoid unsafe shell JSON interpolation, not logged or shared by default.
- The Android native bridge accepts only these fixed seven verbs (the v1 two reads and v2 five actions), from a top-level, exact-origin asset page. All other UX10 shell calls continue to refuse. The ordinary WebUI build is unchanged.

## Quick Settings

1. **Bindhosts** tile: verified actual ACTIVE/PAUSED state, tap to pause/resume with pre/post read-back; automatic busy/error/disabled handling; in-flight request serialization and rapid-tap suppression. It does not claim DNS effectiveness, only the verified generated hosts state.
2. **Update hosts** tile: shows update eligibility and progress state. Tapping opens a native confirmation dialog in the companion. Confirming invokes UX09's detached update coordinator. No silent source updates or cancellation; to view progress, open Rules. Existing update is not restarted.

## Gate / non-goals

- **Hosted CI required:** source + JS tests, `pnpm --frozen-lockfile`, actual shared UX10 bundle check, Android 36 Gradle assemble/unit/lint, SHA-tagged APK artifact. No Gradle on Termux/local.
- **Physical Android 16 required:** module ZIP installed on a disposable/lab path with real UX08/UX09 state and original hosts backed up; QS tiles add, active↔paused, double tap, concurrent updater, root denial, interrupted updater, app process death, and Android Back. Preserve original/IFW state before write acceptance.
- **Next:** scoped source file edits, TrackerGuard app enrollment and owned IFW rule controls with additional versioned contracts and device restore gates; followed by release/signing separately.

**Release state:** no personal release, no signed artifact. Successful hosted compilation is CI qualification, not physical acceptance or release qualification.
