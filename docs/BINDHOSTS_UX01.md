# bindhosts UX01: Material WebUI and curated source catalog

The WebUI now has five tabs: Home, Sources, Apps, Rules (original Hosts editor), and More.
This is a structural UX update, not a frontend framework rewrite.

- **Sources**: opt-in curated catalog with AdAway, Cubic AdBlock, Energized Spark/Blu/Ultimate.
  These presets are disabled by default except any source the user already has configured.
  One catalog-managed Energized tier at a time; user-owned entries are never rewritten.
- **Apps**: R2 installed-package list, scanner preview, opt-in enrollment, exclusions,
  and monitoring controls. No auto-enrollment or automatic blocking by default.
- **Home**: read-only R2 state; existing hosts/status functionality retained.
- **More**: AMOLED black background preference. Material You accent colors are unchanged.
- **Safety**: preset names/URLs are static, root CLI only accepts known preset IDs,
  source changes are staged and atomically replaced, and legacy list/host/log text is
  HTML-escaped. The external favicon service is removed from legacy Sources/Rules lists.

## IMPORTANT safety and limitations

1. Enabling or disabling a catalog preset **edits only sources.txt**. It does not
   update hosts until the user explicitly presses **Update hosts**.
2. Source list URLs were verified against public upstream project documentation,
   not tested for live endpoint availability by the catalog. Network availability
   and list format checks remain a separate acceptance task.
3. The **existing bindhosts --force-update** pipeline is preserved. Its legacy
   TLS fallback, line-based parsing, and nontransactional hosts-file writer are
   not fully hardened in UX01. Do not mistake UX01's source editor atomicity for
   full hosts updater atomicity. A dedicated backend-hardening milestone follows.
4. The legacy Rules editor still has shell-interpolated commands for arbitrary
   manually entered data; use curated Sources for the safer preset path.
5. TrackerGuard Apps uses R2 CLI and per-app preview. Android 16 receiver IFW
   blocking was qualified previously, but this WebUI integration requires device UI acceptance.
6. No localhost HTTP/image replacement server in UX01; plan a later isolated milestone.

## Test / build

    python3 -m unittest discover -s tests -p 'test_source_catalog.py' -v
    python3 -m unittest discover -s tests -p 'test_webui_ux01.py' -v
    sh -n module/source_catalog.sh
    cd webui && pnpm install --frozen-lockfile && pnpm build

All Android-native builds remain on GitHub Actions. The dedicated UX workflow
checks CLI regression tests, JS syntax and Vite WebUI build; the existing
TrackerGuard CI still covers native scanner and module packaging on PRs.
