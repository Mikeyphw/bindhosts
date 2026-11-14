# BH-APP01 P04B-P03 — UX05, UX06, UX07 in the Android companion

Source: PR #19, P04B-P02 `ca00bad3d07414501839b9397642d0ac73675fb5`.

The Android companion reuses the original UX10 screens and implements fixed, typed
commands for the existing read-only UX05 Activity diagnostics, UX06 configuration
backups, and UX07 blocked HTTP / optional HTTPS response controls.

## Read-only operations

- `config_backup_safe.sh`: `status`, `health`, `list`, `imports`, `verify ID`, `preview ID`.
- `ux05_diagnostics.sh`: `status`, `history 1..100`.
- `bindhosts.sh --response status`.

Read outputs use the existing v4 SHA-256-pinned pagination. Every page is bounded
at 3072 bytes, snapshots are capped at 256 KiB, and the entire result is verified
in the Android WebView with WebCrypto SHA-256 before being displayed.

## Fixed write operations

A new v5 root API accepts only these exact data tokens, validated again under root:

- Backup: `create`, `restore~ID`, `export~ID`, `import~ARCHIVE`.
- Diagnostics: `export` (redacted UX05 report only).
- Response mode: `set~off`, `set~transparent`, `set~logo`.
- HTTPS: `https~cert-create`, `https~cert-export`, `https~enable`, `https~disable`, `https~test`.

No arbitrary root shell strings, private file paths, certificate import/install,
URL-interpolation, alternate backends, or free-form command arguments are accepted.
All commands delegate to the existing journaled UX06 and UX07 implementations and
require a recognized receipt in addition to exit code zero. The existing UX10 UI
asks confirmation before restore, backup export, response-mode/HTTPS mutations.
Backup import requires an explicitly selected archive and button press, but
currently has no separate confirmation dialog; physical UX acceptance remains
required before release.
Backend errors are returned as a generic refusal, not raw stdout/stderr.

The original WebUI and KernelSU backends are not rewritten. Backup archives may
contain source URLs or allow/deny entries; export to Downloads requires explicit
existing UX10 confirmation. Certificate trust is not installed or verified by this
app; a local TLS test is **not** evidence of Android trust, and CA installation
must be performed separately by the user in Android settings. App-side opening
of security settings is intentionally still manual, not a shell command.

## Qualification

Source tests include adversarial command denials, non-root disposable backend
fixtures, missing/symlink backends, malformed receipts, snapshot reads and transport
integration. New hosted CI must pass Android 36 compilation, unit tests, strict
Lint, and the WebUI and TrackerGuard workflows at the same exact commit.
Physical Android 16 UX/host restoration, HTTPS/certificate behavior, and signed
release are **not** qualified by source or hosted build tests.
