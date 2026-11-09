# UX02 — Safe hosts editing and fail-closed downloads

This milestone is based on UX01 (`e7789808e6d518ac0296e95a361117d802d32266`), and does not turn on TrackerGuard automatic protection or any HTTP server.

## Changed

1. Replaced the WebUI's raw `sed -i`, `echo`, `cat << EOF`, `rm`, and `cp` mutation paths with the root-only `hosts_config_safe.sh` API. Data is UTF-8/base64 transported, treated as *data*, and cannot become a command. The editor commits validated files through same-directory replacement, with chunking for larger files.
2. Restricts config modifications to an allowlist of the five built-in rules/config files and approved `custom_*.txt` names; verifies ownership assumptions, rejects symlinks and traversal, locks against simultaneous edits, and refuses to overwrite another custom file on rename.
3. New `hosts_update_safe.sh` downloads all configured blocking and allowlist URLs into private staging, enforces HTTPS-only URLs (no `--no-check-certificate`), rejects failed/empty/oversized/HTML-style downloads, parses hosts into canonical entries, and refuses to touch the active file until the full candidate validates.
4. Replaces substring allowlisting with exact domains, with explicit `*.example.org` also matching its base domain and subdomains. Disabled custom hosts mappings are genuinely omitted.
5. Commits the rendered hosts with same-directory atomic rename where the filesystem permits. Bind-mounted `/system/etc/hosts` cannot always be renamed; fallback verifies an in-place write and tries to restore the previous bytes on failure. **This fallback is not power-loss atomic.**
6. A failed backend update now stops `bindhosts run` **before** changing `module.prop` or `bindhosts_state`. No partial source set is treated as a successful update.
7. The WebUI's immediate Unblock action validates domains, and the root-side instant whitelist removes exact entries rather than interpolating into a regular-expression based `sed` command.

## Security and compatibility notes

- `sources.txt` and `sources_whitelist.txt` **require HTTPS** for enabled URLs. Existing HTTP sources must be migrated manually. BusyBox fallback never requests that certificate validation be skipped; actual certificate-verification capability depends on the build and CA store.
- Source formats supported by the updater: classic hosts files (`0.0.0.0 host.example`), plain domain lists, optional custom mappings, and hostname-only allowlists. **Adblock Plus / uBlock filter syntax is not supported**. Source entries returning only that syntax will be rejected rather than silently replacing hosts.
- No source is selected or enabled automatically by UX02. UX01 catalog entries and manual sources remain configured as they were.
- A user may supply `https://... # human label` in `sources.txt`. The catalog's `# source-catalog:id` markers remain intact.
- The source updater fails closed on *any* enabled source failure, rather than overwriting with incomplete rules. This is deliberate; the UI should surface exactly which URL failed.
- Editing file contents and URLs does not automatically refresh active hosts. Run **Update** explicitly after changing sources/rules. Updater emits distinctive `BH_UPDATE_...` diagnostics.
- `stage-commit` limits an individual editor file to 2 MiB; files are transferred in small chunks. If an editor request is interrupted, its temporary stage is inert. `stage-abort` cleans it when the client catches an error.
- Import only accepts paths from shared Android storage (or a test fixture in isolated tests). File types and paths are validated and operations are root-only.
- Protects other managers' IFW files and the existing TrackerGuard rules by leaving TrackerGuard data untouched.

## Tests

- `python3 -m unittest discover -s tests -p 'test_hosts_config_safe.py' -v`
- `python3 -m unittest discover -s tests -p 'test_hosts_update_safe.py' -v`
- `python3 -m unittest discover -s tests -p 'test_webui_ux02.py' -v`
- `sh -n module/hosts_config_safe.sh module/hosts_update_safe.sh module/bindhosts.sh`
- GitHub Actions builds WebUI through the pinned pnpm lock file and packages the native scanners/module. Nothing is compiled locally on Android.

## Runtime smoke test (after hosted CI build and manual module install)

```sh
su -c 'bindhosts tracker json status'
su -c 'sh /data/adb/modules/bindhosts/hosts_config_safe.sh size sources'
su -c 'sh /data/adb/modules/bindhosts/bindhosts.sh --force-update'
```

Check that a failed network fetch leaves the active hosts file unchanged, and verify Sources/Rules editing before enabling any new list. Do **not** rely on the synthetic tests alone for Android SELinux/mount-mode support. The IFW lab already qualified receiver blocking separately; that functionality is not modified.
