# UX06 — private backup and configuration recovery

UX06 replaces the existing raw-shell backup/restore WebUI flow with a fixed root-only backend.

**Saved state**: `/data/adb/bindhosts/.ux06-backups/` (mode 0700) holds immutable-by-convention snapshots and SHA-256 manifests. `/.ux06-restore-pending` within the persistent state retains **previous** configuration bytes during restore; boot service checks it and attempts recovery before regular background tasks. Do not delete pending recovery journals manually.

**Commands** (`su -c 'sh /data/adb/modules/bindhosts/config_backup_safe.sh ...'`): `status`, `health`, `list`, `create`, `verify SNAPSHOT`, `preview SNAPSHOT`, `restore SNAPSHOT`, `recover`, `export SNAPSHOT`, `import bindhosts-backup-SNAPSHOT.tar`.

**Safety boundaries**: Five fixed config names only. The export includes raw configuration URLs and rules: Downloads is less private than root storage. Import accepts only Downloads basenames, only a 6-entry uncompressed tar with regular files, exact names and checksums. SHA-256 is integrity detection, not a source signature. Every file is syntax validated prior to restore. A restore is multi-file transactional with a recovery journal and attempted rollback; it is NOT filesystem-atomic across five files under power loss.

**Source health**: Counts enabled, disabled and duplicate lines without exposing URLs or domains. Duplicate count is an advisory read-only check, not an automatic rewrite. No source is enabled, removed or deduplicated automatically. For content changes, explicitly run Update hosts after reviewing configuration.

**Default behavior**: No snapshots made automatically, no restore automatically, no backup files uploaded to any server, no network I/O, and no modification of TrackerGuard ownership or existing hosts content.

**CI gate**: UX06 native shell and WebUI syntax, 10+ isolated backend tests, legacy UX01–UX05 suites, hosted Vite and Android module packaging. Device acceptance remains necessary before a release.
