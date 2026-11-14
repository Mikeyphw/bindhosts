# UX09F — final physical acceptance and release gate

Parent: UX09E PR #16 at `bd556b508e5e6563858ca08890cdaea245f1f622` (green hosted UX09E builds). Source-only changes; all kernel/root writes require separate human consent.

## Grounded inputs
- UX09E module: GitHub Actions run `43546943742`, artifact `bindhosts-trackerguard-r1` on exactly the UX09E SHA. ZIP contents `module.prop`, WebUI, 12 source-pinned UX09/HF04/core scripts and ARM64 binaries are verified against the pinned Git tree.
- R3 lab: run `42670772403` at `c76658efeece6a5abb791d721e18b6ee34a7784b`, `trackerguard-ifw-lab-v1` and `trackerguard-ifw-lab-v2`; APK name/version (1 and 2), zero requested permissions, and distinct SHA-256 are checked with Termux `aapt` before R3 writes.
- Read-only probe: Android API, ABI, root UID, SELinux mode, actual PackageManager inventory (not help text), installed helper hashes, hosts status, UX09E mount and TrackerGuard R3 read-only checks.

## Final required gates
| Gate | Evidence | Fail-closed condition |
|---|---|---|
| mount-probe | Source-pinned `hosts-mount-acceptance.sh --read-only` streamed to root child | Read-only mount/writer checks unavailable |
| ui | UX09E human-observed Sources, Rules, More plus read-back verified toggle, source restoration, real terminal/update & dedup counters | Failed step, changed rules, incorrect receipt |
| manual-matrix | 12 explicitly user-observed app surfaces and failure states | Any skipped or failed stage |
| mount-live | Source-pinned mount test `--probe-live --accept-risk` with explicit consent | Byte restoration not confirmed |
| rules-live | Human inserts and removes isolated `.invalid` blacklist, whitelist and custom entries | Any unexpected rule-file drift, original bytes not restored |
| backup-live | Human creates/verifies/restores only the new private backup | Original rules not byte-for-byte restored |
| response-live | Human toggles HTTP-only mode and restores original setting | Wrong response read-back or hosts state drift |
| r3-probe | Source-pinned R3 read-only inspection | Root/lab signature unavailable |
| r3-live | Source-pinned R3 lab installer/update/uninstall, IFW checks and independent cleanup | Missing APKs, failed R3 marker or cleanup |

The final summary remains PENDING until every required gate has a matching PASS receipt for this source revision. If the lab is already installed or non-empty TrackerGuard state would be altered, the R3 script refuses before installation. R3 cleanup failure is an explicit block, not a silent retry. No actual device test runs in hosted CI.

## Important exclusions and scope
The UX09F harness qualifies core features on an API36 arm64 device but does not install/trust Android CA certificates, modify SELinux enforcement, change other apps' IFW rules, or assert arbitrary apps' compatibility. Test screenshots are opt-in, local/private and potentially sensitive. The HTTPS status and trust warnings are visually checked; end-to-end Android HTTPS trust is *not* established without a separately scoped security experiment.

## Hosted qualification
Both `bindhosts WebUI UX and sources catalog` and `TrackerGuard R1 native scanner, IFW tests and module ZIP` must pass for the same UX09F commit. Test runner fixtures exercise refusals for unsafe serials, missing/drifted artifact hashes, PM-help mistaken for inventory, unverified script pins, unapproved live writes, missing evidence and false all-green status.

Live acceptance additionally requires **API36**, **arm64-v8a**, **SELinux Enforcing**, and all pinned module scripts to match. Unexpected targets remain read-only and unqualified.
