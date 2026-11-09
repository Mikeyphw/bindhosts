# bindhosts UX07 — opt-in HTTPS blocked-image responses

Baseline: TrackerGuard R3 PR #11 head `c76658efeece6a5abb791d721e18b6ee34a7784b`.
Target: v2.1.5-tg.0.11 (21611). PR is stacked onto R3 until R3 receives live acceptance.

## What this does

UX07 extends the existing UX04 localhost HTTP blocked-image server (port 80) with a
separate TLS responder (port 443). Both serve only a fixed transparent 1×1 GIF or
bindhosts SVG. They do not proxy, inspect, forward or log application requests.
The TLS binary is self-contained Go standard library (`crypto/tls`, `crypto/x509`,
`net/http`); GitHub Actions builds it for Android arm64-v8a, armeabi-v7a and x86_64.
No Go toolchain or Termux process is needed on the installed Android device.

## Security and trust boundaries

- **Off by default.** Generating a CA does not start a server and does not install
  a trusted certificate. Enabling TLS is a distinct operation; Android certificate
  installation is a separate, manual OS action.
- A random P-256 local CA is generated **on the phone** under
  `/data/adb/bindhosts/.ux07-tls/` (0700). Its key `ca.key` is mode 0600 and is
  never exported. The public CA `ca.crt` is exported to Downloads only on request.
- The TLS server listens only on **127.0.0.1:443**. It issues short-lived
  per-SNI certificates only for valid domain names in the active hosts file with
  exact `127.0.0.1 name # bh-response` records, or `localhost` for diagnostics.
  Manual mappings, unblocked names and arbitrary SNI names are rejected.
- A user-trusted CA expands trust in that Android profile. This is a powerful
  security capability: do not install the CA unless you understand the risks.
  It is not silently added to Android's system CA store, and the module never
  changes Android TLS settings or bypasses pinning.
- Android apps targeting newer SDKs frequently do not trust user-added CAs;
  Chromium variants, ECH, QUIC, DoH, HSTS and certificate pinning can prevent
  image replacement. **This is not universal HTTPS interception or a promise
  that every blocked website displays an image.** The TLS image is not shown
  until that specific client trusts the user-installed CA and permits the TLS
  connection.
- Disabling HTTPS **does not remove a CA already installed in Android**. Remove
  it manually in Android Settings → Security → Encryption & credentials → Trusted
  credentials → User, if you do not want that extra trust to remain. Uninstalling
  the module does not revoke an OS-installed trust anchor either.
- HTTPS serving is fail-closed and independent of HTTP. On TLS start failure the
  HTTPS enable flag is disabled while the existing HTTP image mode remains
  usable. If HTTP itself cannot start at boot, UX04 reverts managed hosts to
  ordinary 0.0.0.0 blocking. No external IP binding, upstream fetch, request
  telemetry or arbitrary certificate export is provided.

## User flow (KernelSU WebUI)

Sources → Blocked-page image → select **Bindhosts blocked image** (or GIF).
Update hosts first to create marked hosts sections. Then in the HTTPS panel:

1. Generate local CA (separate explicit confirmation).
2. Export **public** CA `.crt` to Downloads (separate explicit confirmation).
3. Optionally verify the printed SHA-256 fingerprint and manually install the
   public CA certificate in Android Settings. Android may show prominent warnings.
4. Enable HTTPS responses (separate explicit confirmation).
5. Test local TLS and image response. **This test verifies the TLS handshake
   against the saved public CA, not the Android trust store or browser.**
6. Test a blocked HTTPS domain in a client that you know trusts that CA.

A simpler CLI flow (run as root via `su -c`):

```sh
sh /data/adb/modules/bindhosts/bindhosts.sh --response set logo
sh /data/adb/modules/bindhosts/bindhosts.sh --response https cert-create
sh /data/adb/modules/bindhosts/bindhosts.sh --response https cert-export
sh /data/adb/modules/bindhosts/bindhosts.sh --response https enable
sh /data/adb/modules/bindhosts/bindhosts.sh --response https test
sh /data/adb/modules/bindhosts/bindhosts.sh --response status
sh /data/adb/modules/bindhosts/bindhosts.sh --response https disable
sh /data/adb/modules/bindhosts/bindhosts.sh --response set off
```

The full path above is intentional: root's PATH does not always include the
bindhosts symlink. The server is not a generic TLS proxy, so it won't fix site
errors for every blocked HTTPS page. HTTPS server deployment requires physical
Android 16/KernelSU port 443 and SELinux acceptance after CI builds.

## Hosted acceptance gates

- Host Go TLS test: CA creation, no overwrite/symlink, managed SNI restriction,
  actual TLS handshake and image response, HTTP/HTTPS mode coexistence,
  rollback to ordinary hosts, and no silent CA installation.
- Native Android Go executables: arm64-v8a / armeabi-v7a / x86_64, installed
  executable by KernelSU's `set_perm`.
- Existing UX01–UX06 and TrackerGuard R0–R3 regressions and Vite WebUI build.
- Device confirmation: `https_server=running`, `android_trust=not_verified`,
  local test PASS; separately inspect manual browser trust behavior.

The UX07 overlay is source-pinned and its installer **does not merge R3 PR #11
without device acceptance**; it opens a stacked UX07 PR against R3 while R3 is
open, or against master if R3 was already merged with the exact pinned tree.
Push/PR creation/CI watch are automatic, no force-push or auto-merge UX07.

## HF01 audit corrections

- The WebUI now displays the full 64-hex SHA-256 fingerprint of the generated public CA, rather than only showing `certificate=present`; it is visible under Sources → Blocked-page image and via the root CLI `--response https cert-status`. It also offers a fixed Android Security Settings shortcut (it does not install or trust the CA automatically).
- Public certificate export is performed by the native Go TLS utility with `O_CREAT|O_EXCL`, exact fingerprint-derived basename verification, `fsync` and cleanup if writing fails. A pre-existing file or symlink cannot be overwritten, including if it appears between validation and creation.
- A failed response-status request clears the WebUI status rather than leaving a stale trust-looking indicator.
- Additional offline integration covers certificate fingerprint output and export no-clobber against a real file and symlink.

Still not claimed: installing CA through an Android WebUI API, cert trust inside arbitrary apps, pinning bypass, QUIC/ECH compatibility, or live Android 16 port-443/SELinux/browser acceptance.
