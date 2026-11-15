# BH-APP01 P05 HF01 + P04B · Folded management bridge

## Exact source and failure

- P05 parent: `3ea4edf9888057f3340c42ab6039ee00d4d27e79`, PR #19.
- Run 43641875820: `assembleDebug` succeeded; `lintDebug` refused `UpdateTileService.startActivityAndCollapse(Intent)`.
- This combined overlay **includes** HF01's narrowly scoped pre-API34 Lint exemption. No global Lint suppression or baseline.

## Added integration

P04B uses the **same UX10 UI**. It maps a finite set of exact KernelSU command strings to a native v3 JSON broker, then reuses the existing root-side safe backends:

- Rules: bounded read, custom-file inventory, add/remove/toggle/replace, stage begin/chunk/commit/abort, safe custom rename/import/delete.
- Sources: catalog status, applied status, manual inventory and atomic preset batch.
- TrackerGuard: current JSON status/rules, installed user packages, per-package preview, enroll/unenroll/exclude/include and confirmed monitor actions.
- Existing P05 hosts pause/resume, update progress, safe update tile remain intact.

Java accepts exactly three message keys for the six management operations (`id`, `op`, `arg`), validates the ASCII argument and only then base64-encodes it into a **fixed** root command. The module script independently checks the finite verb/arity/charset, rooted module paths, and successful backend receipt. No arbitrary paths, shell text, `eval`, `sh -c`, backup restores, HTTPS replacement, reboot, or force updates are exposed. Responses are bounded to 4800 bytes and base64-encoded; overflow refuses rather than silently truncating.

## Not yet fully qualified or supported

- UX10 live-screen/Android 16 physical acceptance, root denial and lifecycle races are **pending**.
- Large configuration and TrackerGuard inventories above 4800 bytes refuse; they require a future paginated/read-back API (not falsely reported as empty).
- Full parity for all custom file-selector paths, backup/restore, HTTPS replacement, advanced diagnostics, and every More-page command is **not** claimed.
- Developer `--test` exercises non-root synthetic fixtures; it cannot qualify a real rooted device.
- GitHub Actions (not local Gradle) must build the APK, run Lint, and produce SHA-pinned artifacts. Release/physical acceptance is separate.
