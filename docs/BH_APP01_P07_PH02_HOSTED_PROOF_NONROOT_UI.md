# BH-APP01 P07 PH02 — independently verified hosted evidence and physical non-root UI smoke

## Provenance

Parent SHA: `ec761f5d3085607d2b391338359dd8df18c4d24e`; PR #19. Prior HF05+PH01 CI at this exact parent: Companion Foundation, WebUI, TrackerGuard, and API36 hosted UI all passed. This PH02 overlay must be **requalified at its own new HEAD**; passing CI on the parent does not qualify the new commit.

## Host-only independent gate

`scripts/ci/bh_app01_p07_ph02.py hosted` verifies live PR #19 identity; matching branch/base; local clean HEAD; the **latest** PR-triggered run for each of the four fixed workflows has status `completed` and conclusion `success` at the same exact source SHA; matching unexpired hosted evidence artifact containing the exact debug APK; and exact re-derivation by `bh_app01_p07_signoff.qualify` from downloaded PNG, XML, APK identity, cold-start QS receipt and native Cancel log. The tested APK is exported privately with its checksum verified, but no install is performed. No arbitrary GitHub endpoint, shell string, secret, or device command is accepted.

A passing hosted gate produces private SHA-bound receipts; it does **not** certify code signing, reproducible builds, physical-device tests or release.

## Physical non-root gate

`ui-smoke` additionally invokes PH01 preflight and compares the installed physical APK hash to the independently checked hosted artifact. It rejects absent/incorrect APKs, wrong ABI/API, emulators, multiple ADB devices and invalid QS services. Only explicit `I_AUTHORIZE_NONROOT_UI_SMOKE` enables the UI transaction. Finite `adb` argv: targeted ActivityManager QS confirmation, one named UIAutomator XML file, readback, validated Cancel touch, Android activity readback, own-file cleanup. No root, `adb install`, hosts update, app data clear or IFW mutation.

**No screenshots or unredacted UI hierarchy are persisted by PH02**; the local receipt contains a SHA-256 hash of the transient XML instead. Device UI is changed by opening the app, and one temporary `.xml` is created and removed. Do not run without accepting this narrow interaction.

Full P07 physical acceptance remains pending the user-authorized device-write acceptance for hosts restoration, TrackerGuard foreign-IFW integrity, SAF and QS races. P08 signing and P09 parity drift likewise remain pending. An INCONCLUSIVE / REFUSED outcome is never represented as a pass.

## Adversarial regression coverage

`test_bh_app01_p07_ph02.py` uses in-memory fake GH/ADB responses (no external actions) for wrong PR/branch/source, stale and latest-failed CI runs, missing/expired artifacts, inconsistent hosted receipt, missing/malformed/ambiguous Cancel UI, wrong serial, missing opt-in, wrong APK/preflight, and failed on-device cleanup; also tests successful exact Cancel coordinates and 0600 private receipt creation. This test is automatically executed by the existing Companion Foundation workflow's `unittest discover` command. All Gradle compilation stays GitHub-hosted.

## Tested debug APK retention

The hosted emulator script now copies the *same* APK used by Android instrumentation into its SHA-bound evidence archive; the signoff verifier recomputes SHA-256 from those actual bytes and rejects a missing or replaced APK. PH02 independently downloads that exact tested APK to a `0600` private file. A separate Foundation-workflow debug build may use a different ephemeral debug signing key and **must not** substitute for this tested APK. Installation, signing migration and rollback are deliberately not automated.

## Exact-SHA CI triggering

The original WebUI workflow has restrictive `pull_request.paths` filters that exclude P07-only changes. PH02 adds finite P07 script/test/docs selectors so **all four required workflows** can qualify the exact new HEAD without manual dispatches. TrackerGuard already triggers on all pull requests.
