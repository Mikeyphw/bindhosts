# UX08: explicit hosts blocking controls

The previous Rules-page FABs invoked `--action` (checksummed toggle/update) and `--force-update` (unconditional update). They were unlabelled and UI completion only observed process exit, not state.

UX08 replaces them with an explicit Blocking controls panel: Pause blocking, Resume blocking, Update hosts, Refresh status. The UI reads `--hosts-control status` before/after actions and requires both a zero exit code and exact backend success marker. It does not claim that Android DNS resolution was physically verified merely from a generated hosts file.

The root-only `hosts_control_safe.sh` delegates pause/resume to the existing journaled `hosts_reset_safe.sh toggle`; the original hosts remain in `bindhosts_backup` until a successful resume. It refuses requests inconsistent with current state. The update pipeline and legacy `--force-update` refuse while paused, including scheduled updates. Pause/resume acquire the same lock as hosts updates, preventing races. The legacy updater no longer unconditionally removes the pause backup during cleanup. Status performs no writes or initialization. After a verified pause/resume, the backend also refreshes the Home-page module description (best effort); this metadata is not used to declare the hosts action successful.

This change affects hosts-file blocking, **not** TrackerGuard IFW monitoring/enrollment. R3 device qualification is independent and still pending. No Android install or reboot is performed by this overlay.
