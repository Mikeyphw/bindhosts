# BH-APP01 P04 — Shared UX10 UI bundle (read-only companion gate)

Source branch: `feature/bh-app01-p00-p03-companion-foundation-20261114`
Source HEAD: `76df5c709053db73b85f10de8230e539064c3db4` (HF04, PR #19)
Base UX10: `03974508b6743520ffe576869fa86cb5cf45a55d` (PR #18)

## Implemented

- The companion reuses the existing `webui/index.html`, `webui/index.js`, `webui/route.js`, and six UX10 page modules. The normal module WebUI build (`vite.config.js`) remains untouched.
- A second Vite config builds the same UX10 entrypoint under `android/companion/app/src/main/assets/ux10` **only in GitHub Actions**, before Gradle. The resulting assets, including locale resources, are verified by `scripts/ci/bh_app01_p04_bundle_check.py` and packaged into the debug APK.
- The companion-specific Vite aliases intercept KernelSU and WebUI-X imports. The KernelSU adapter recognizes exactly two literal commands: hosts-control status, and module.prop display. Both map exclusively to `hello`/`status` in the pre-existing native read-only bridge. The displayed module.prop text is synthesized from verified read-back with explicit limitations; the original file is not fetched.
- All other shell operations, including hosts updates, TrackerGuard edits, settings, installers, TCP dump, reboot and streaming spawn, fail closed with a read-only error. User-provided strings are never interpolated into root commands.
- WebView navigation and subresources are restricted to `https://appassets.androidplatform.net/assets/ux10/`. No INTERNET permission is declared. UX10 local storage is enabled for language/appearance preferences. A native banner prominently identifies the preview as read-only, outside the WebView's control.
- Android Back delegates to UX10's existing navigation/dialog handler and exits at Home.

## No false parity claim

P04 is **shared source and navigation parity**, NOT 1:1 functional parity. The existing KernelSU WebUI remains the full-featured writer. P04 Android preview is a safe read-only shell. Rules, source catalog, TrackerGuard, backups and other editing controls are displayed using the same UX10 pages, but read paths outside the native allowlist and all device mutations are unavailable. The companion must never report those features as functional. The next stage must introduce a versioned, individually validated read/write operation API with rollback and real physical acceptance; it must not bridge arbitrary command strings.

## Gates

- Host-side shell and Python tests and Node refusal/back tests (no local Gradle).
- GitHub Actions must build UX10 using the frozen pnpm lockfile and verify the generated assets before Gradle compiles the app.
- The Android job must pass `:app:assembleDebug :app:testDebugUnitTest`, produce SHA/commit receipt, and upload a nonexpired debug APK.
- Real Android 16 WebView load, Home/Rules/Apps/More navigation, no unintended device writes, and Back behavior remain physical-device gates. Do not sign off a personal release based on source tests alone.
