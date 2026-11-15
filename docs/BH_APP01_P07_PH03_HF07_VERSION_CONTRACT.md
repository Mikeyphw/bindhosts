# BH-APP01 P07 PH03 HF07 — version regression contracts

Parent PR #19 HEAD: `73d385833f35184ac22d26f089a8c68ab1292d20`.

## Exact CI diagnosis

- `bindhosts-ux-ci.yml` run 43680817429: UX02 test pinned `version=v2.1.5-tg.0.11` despite the legitimately bumped module `v2.1.5-tg.0.12`.
- `trackerguard-ci.yml` run 43680817448: UX05 test pinned `versionCode=21611` despite `21612`.
- `bh-app01-module-with-apk.yml` run 43680817483: **correctly** refused when the required WebUI check failed; no packaging policy is weakened.

## Contract change

UX02 and UX05 now parse the actual version and require the package version suffix to match its `versionCode` (21600 + suffix), with an established lower bound of .11. The separate update.json stable-release reference is deliberately unchanged; it is not a license to claim an unreleased APK has been signed or published.

New `tests/test_bh_app01_p07_hf07_version.py` executes both real contracts with .11, .12, and .13 synthetic versions and refuses mismatches or version regression. No Android execution is used.

## Publishing and qualification

This is one source-pinned hotfix commit on the existing PR. All five required workflows remain mandatory. The GitHub Actions module workflow still waits for **four successful exact-head workflows** and verifies the same hosted-tested APK before emitting the module ZIP.

Direct `gh run watch --exit-status` and `gh pr checks` output is preserved. No Gradle run on Termux; no automatic physical device mutations, no root grant, no merge or force-push. Physical Android16 and release signing are separate gates.
