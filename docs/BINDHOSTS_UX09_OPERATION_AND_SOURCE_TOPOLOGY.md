# UX09 — verified operation feedback and Sources topology

Parent: TrackerGuard R3 HF04 PR #14, commit `2645804db1866a4c6c2142cea7b1dce1016f8ef7`.

## UI and workflow

- The Rules page retains UX08's explicit Pause/Resume buttons and read-back checks. The Update action opens the shared full-height **Hosts update terminal** rather than claiming success with a generic toast.
- The Sources tab is organized into Presets, My sources and Advanced. AdAway and Cubic are separate selections; only one catalog-managed Energized tier can be selected. Manual URLs remain independent and are toggled through the existing root-side validated editor.
- The catalog saves a *complete set of presets* atomically. `Save selection` does not update active hosts; `Apply changes & update hosts` first saves, then starts the shared update. A stored SHA-256 and validation timestamp distinguish applied from pending source sets; an unknown/unavailable fingerprint is never misreported as current.
- HTTPS blocked-page response controls and all UX07 trust warnings were moved into a collapsed advanced section at the top of **More**. No certificate is generated, installed or trusted by default.

## Actual update progress and measurements

- A detached, root-controlled worker runs the existing UX08 read-back-verified `--hosts-control update`. A root-only private journal carries fixed progress stages; the WebUI polls state and events, renders with `textContent`, never `innerHTML`, and does not interpolate source content into shell command strings.
- Events: PREPARING, DOWNLOADING (index only), PARSED, SKIPPED_DUPLICATE_URL, DEDUPLICATING, ALLOWLIST, GENERATING, COMMITTING, STATS and DONE/UNCHANGED/FAILED.
- Statistics are measured from the actual staging files: raw parsed blocked rows, duplicate blocked lines removed with `sort -u`, unique rows, allowlist exclusions, final block rows, downloaded source files, repeated exact URLs skipped, and changed vs unchanged hosts.
- Exact repeated HTTPS source URLs are downloaded once within the blocking or allowing source category, without altering manually managed URL entries. A URL shared between blocking and allowing modes is fetched separately so it is parsed in the correct mode.
- The operation viewer is **not** a simulated percent progress bar. Its detailed events don't expose URLs, domains or application identities. The backend's root-private raw log can contain source URLs and is not included in user-visible or exported telemetry.
- Close hides the view but does not request cancellation. Android/KernelSU may still terminate background processes; a missing worker is surfaced as INTERRUPTED, not success. Stale/interrupted operations require manual inspection rather than automatic reruns.

## Safety and compatibility

- Changes are strictly scoped to hosts updates and the existing Sources page; **TrackerGuard R3/HF04, IFW ownership, module installation, and the physical device** are unchanged.
- Source editor, catalog and UX09 batch writes share the serialized `.hosts-update.lock` for catalog-managed changes. The existing journaled hosts writer retains fail-closed semantics and the backup used for Pause/Resume.
- The source digest is captured *before* fetch and published only after a verified successful/unchanged update. A concurrent external edit remains pending.
- Existing UX01/UX03/UX04/UX07 static UI tests are updated only to follow the relocated UI and new atomic preset pathway; their security and trust assumptions are preserved.
- No automatic SELinux policy changes or certificate installations. No live Android 16 acceptance claims.

## Required hosted and physical acceptance

1. Run `python3 -B tests/test_hosts_ux09.py` and `python3 -B tests/test_hosts_update_ux09.py`, plus UX01, UX02, UX03/UX04, UX07, UX08 and source catalog tests.
2. Run the two existing GitHub workflows for the exact UX09 commit; compile WebUI with pnpm and package the module via hosted CI only.
3. After a separate explicit KernelSU install and reboot, verify Rules update terminal and Pause/Resume, Source preset atomicity and pending state, manual ownership, repeated URL behavior, source failures, summary counts, and HTTP/HTTPS response settings under More.
4. Qualify TrackerGuard R3 lifecycle separately, only after its dedicated root PackageManager transport review. No automatic merge or device writes.
