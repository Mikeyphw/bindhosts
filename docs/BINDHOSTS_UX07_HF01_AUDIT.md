# UX07 HF01 — promise-by-promise audit

| Promise | Implemented evidence | Remaining gate |
|---|---|---|
| Local TLS 127.0.0.1:443 | `native/blocked_response_tls/main.go`, `serve` and SNI tests | Android 16 port/SELinux |
| CA generated per device, private key stays root-only | `genCA`, `readPrivate`, 0600 tests | Android file labels |
| Public CA export and manual Android installation | `cert-export` O_EXCL, public PEM; explicit Security Settings shortcut | Manual OS trust action |
| CA status/fingerprint | 64-hex SHA-256 in root CLI and WebUI; no claim of trust | Browser-specific trust |
| Image/GIF response | Go GET/HEAD responder and mode tests | Physical-browser rendering |
| Only managed domains get generated leaf certificates | SNI restricts `# bh-response` hosts mappings plus localhost diagnostic | Dynamic app/network stack variations |
| Off by default, no auto CA install | backend flag guard and confirmation UI | Device mode persistence |
| Fail-closed after server failure, keep HTTP intact | UX04/UX07 response integration and tests | Reboot/runtime failure simulation |
| ARM64/ARMv7/x86_64 binaries | hosted cross-compiler CI, installer executable permissions | GitHub Actions and device install |
| Source-pinned consolidated installer | exact R3 blob pins, SHA256 payload, old UX07 branch safe upgrade, commit/push/PR watch | User Termux execution |

Caution: The CA is a broadly trusted root if manually added to Android. HTTPS replacement is not universal; Android user-CA policy, pinning, QUIC/ECH and browser behavior can defeat it. No automated installation, automatic merge, or production release is performed.
