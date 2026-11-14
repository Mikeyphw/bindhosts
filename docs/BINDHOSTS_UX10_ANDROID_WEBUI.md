# UX10 — Android KernelSU WebUI mobile redesign

Parent branch: UX09F PR #17 (`957614232d7d95f4bbb204013a3621e5e005e4f6`).

- Four bottom tabs: Home, Rules, Apps, More. Existing `catalog` route stays internal; it opens with **Manage presets** from Rules and has a visible **Back to Rules** button. Android Back from the internal page also returns to Rules, and the Rules bottom-nav icon remains selected.
- The global Update hosts confirmation is a simple, history-managed overlay, not an animated Material `md-dialog`. Both Cancel and Continue hide it immediately and settle the same promise exactly once. Android Back cancels it. No operation is started on Cancel.
- The update terminal is a full-height mobile view with touch-friendly Close and a source-by-source transcript. A live `DOWNLOADING` event includes either a fixed public preset name + hostname or a sanitized hostname for custom lists; user-info, path, query string and URL fragments are not disclosed. `PARSED` shows per-source bytes and parsed entries. Aggregate deduplication statistics remain actual backend measurements. No fabricated percentages.
- The KernelSU module's dynamic description appends `app trackers blocked: N (configured IFW rules)` from TrackerGuard's owned rule database. This is a count of configured blocked components, **not** a claim about observed block events. Refresh on boot, manual changes, monitor cycles, and Pause/Resume. The Home card uses the same semantically precise label.
- Preserve prior UX09 backend audit and UX09F physical acceptance. Neither installing the module nor mutating the device is part of this source overlay.
- Android WebView is the supported runtime. No extra desktop layout or desktop-only interaction.

Required physical tests: tap both confirmation choices, Android Back, real source-by-source update transcript, close/reopen while running, nested presets Back, manual-source ownership, tracker description after adding and removing a lab IFW rule, screenshot on Android API 36. Do not qualify device/UI behavior on hosted source tests alone.

## HF01 post-implementation UX audit

- Enforced a pending-choice confirmation for *all* navigation out of Sources; a confirmed discard restores the last saved selection, and an interrupted manual edit cannot silently erase unsaved preset choices.
- Energized now uses mutually exclusive radio controls with an explicit **None** option; tapping a preset card is supported.
- Added bounded source-specific failure events, named parsed results, human-readable operation stages and a current-source status. The source journal never copies raw full URLs or secret query parameters.
- Fixed terminal header wrapping for 320-pixel portrait Android WebViews. Browser-simulated 320/393/412 px audits passed; real on-device acceptance remains pending.
