# BH-APP01 P00–P03 foundation — source-only delivery

Source base: `Mikeyphw/bindhosts` PR #18 `03974508b6743520ffe576869fa86cb5cf45a55d`. This is a **stacked** increment, not an alteration of PR #18. Upstream Android companion research reference: `itejo443/BindHosts-app` GPL-3.0, v1.0.2 (2025-02-05). **This new Java scaffold is independently authored; no original companion source files are copied.** It uses a distinct package ID `com.mikeyphw.bindhosts` and does not claim to upgrade the signed official app.

## Included

- `contracts/bh-app01-v1.json`: versioned *read-only* API manifest (`hello`, `status`).
- `module/companion_api.sh`: fail-closed, finite root dispatch for module handshake and verified hosts/update read-back. This does **not** edit root state.
- `webui/runtime/companion_transport.mjs`: typed manager/native read-only adapters and response validation. This module is intentionally **not** wired to UX10 pages yet; a full conversion of direct exec/spawn calls is P02 remaining work.
- `android/companion`: independently authored Android WebView shell, private bundled status screen, origin-checked main-frame message listener, read-only runner, and status-only Quick Settings tile. No `addJavascriptInterface`. The native app currently does **not** package the full UX10 Vite bundle.
- `.github/workflows/bh-app01-foundation.yml`: actual hosted source verification and Android SDK36 APK compilation. Android Gradle is never run on Termux.
- Tests for hostile unknown verbs, state parsing, root path override, malformed replies, and safe transport calls.

## Source inventory / parity trace

| UX10 route | Verified source | State in this increment |
|---|---|---|
| Home | `webui/page/home/home.*` | Backend `hello`/`status` only |
| Rules | `webui/page/hosts/hosts.*`, `webui/utils/hosts_controls.js` | Read-back only; edits/pause/resume gated |
| Sources | `webui/page/catalog/catalog.*` | Not yet wired |
| Apps/TrackerGuard | `webui/page/apps/apps.*` | Not yet wired; IFW ownership unchanged |
| More/HTTPS/backups | `webui/page/more/more.*` | Not yet wired |
| Activity/diagnostics | `webui/page/activity/activity.*` | Update state only; event viewer gated |
| Update terminal | `webui/utils/hosts_operations_ux09.js` | Read-only operation state |
| Quick Settings | external original `itejo443/BindHosts-app` | New status-only tile; **not** pause/resume yet |

## Supported behavior and blockers

This increment is **not 1:1 parity**, not a certified full-feature companion, not a signed release, and not a device acceptance pass. The status tile shows active/paused/inactive/module-disabled states from fresh root reads and opens the app when tapped. All writes remain prohibited until P01 mutation receipts, strict validation, P02 parity migration and P05 race-proof QS controls exist.

**Security boundary:** the Android bridge only accepts validated `hello`/`status` messages from the packaged `appassets.androidplatform.net` main frame; all external navigation and frame messages are refused. There is no arbitrary JavaScript-to-shell bridge. The root runner constructs only constant allowlisted scripts/verbs. The standalone app has no `INTERNET` permission and native content CSP disallows network connections, navigation forms and frames. The independent tile does not guess state from the fifth output line or persist a fake active state.

**Production compatibility:** `companion_api.sh` must be installed by a separately qualified module ZIP before the native app can handshake. Installing the preview APK by itself must report unavailable. No automatic module installation, no certificate changes, no app uninstall, and no IFW writes are performed by this increment.

## Required subsequent consolidated increment

1. Replace all UX10 page-local `kernelsu-alt` direct `exec/spawn` calls with typed transport commands; unify manager/native operation handling, preserve 1:1 tests.
2. Extend root-side JSON schema to validated, journaled writes with bounded operands and true idempotency; no user-defined `sh -c`.
3. Package the exact built Vite frontend into the native app using CI source digest checks.
4. Implement two QS tiles: verified pause/resume with locking and read-back; update tile opens in-app explicit confirmation. Add optional notification status.
5. Run hosted API36 journeys and separate explicit physical API36/arm64 KernelSU acceptance; keep PR #18 UX10 physical qualification independent.

## Validation

Run `python3 -m unittest discover -s tests -p 'test_bh_app01_*.py' -v`, `node tests/test_bh_app01_transport.mjs`, `sh -n module/companion_api.sh`. The Action builds with the pinned hosted Gradle 8.11.1 and Android SDK36; do not run Gradle locally. Actual APK build status is not known until a GitHub Actions run exists at the applied SHA.
