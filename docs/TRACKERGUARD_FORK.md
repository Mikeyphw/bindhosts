# TrackerGuard fork — R0

Upstream: https://github.com/bindhosts/bindhosts (WTFPL v2, see `LICENSE`).
Pinned base: `e83bde99d5ea4be02eee78c43145d89490a9cda7` (master, 2026-11-08).
Target fork: `Mikeyphw/bindhosts` (retains the original Git history).

## R0 scope (implemented)

- Existing bindhosts hosts-file protection, updater, WebUI, and root-manager modes remain intact.
- `bindhosts tracker` dispatches to an opt-in IFW engine.
- Explicit service, receiver, and activity component blocking for installed user apps.
- Per-app or all-owned-rule restoration; foreign IFW XML files are never modified.
- Reapply saved explicit rules at boot. No polling or event monitoring.
- Upstream canary installer disabled to prevent accidentally replacing the fork.
- Root-manager update URL points to the fork rather than upstream.

## Example (on a test user app)

```sh
su -c 'bindhosts tracker status'
su -c 'bindhosts tracker add com.example.app service com.example.sdk.AnalyticsService'
su -c 'bindhosts tracker list'
su -c 'bindhosts tracker restore com.example.app'
```

R0 requires an **exact known component name**; it does NOT discover trackers by parsing apps.
Do not assume any component with `Analytics` in its name is safe to block. Use App Manager
or other tooling to verify the real manifest and component role before adding a rule.

## Security and data

- Persistent explicit-rule database: `/data/adb/bindhosts/trackerguard/rules.tsv`.
- IFW file owned exclusively by this fork: `/data/system/ifw/bindhosts_trackerguard.xml`.
- The engine rejects writes over another owner's file, only allows user apps,
  validates XML-included strings, and uses atomic same-directory replacement.
- Uninstall removes only its own IFW file (based on an ownership marker).
- Some Android builds can restrict IFW processing or fail to reload rules. Runtime
  behavior must be verified on device; writing a rule is **not proof** it is enforced.
- IFW does not block network analytics from inside a process. Hosts blocking
  continues to handle known domains, subject to DNS/network bypass limitations.
- If App Manager separately blocks the same component, restoring this fork's rule
  won't undo App Manager's independent block.

## Next milestones (not implemented in R0)

1. R1: Instrumented Android 16 manifest inventory engine + source-grounded signatures,
   dry-run preview, safe per-app auto-block for opt-in user apps.
2. R2: Post-install/update watcher (event-driven with polling fallback) and reconcile,
   exclusions, JSON status, and rollback after APK changes.
3. R3: WebUI TrackerGuard page; maintain upstream bindhosts UX and controls.
4. R4: GitHub Actions Android 16 emulator acceptance and root/IFW integration,
   source synchronization, standalone releases.

**Important:** Original bindhosts's WebUI continues to work but does not yet expose the
TrackerGuard controls. The root CLI is the supported interface in R0.
