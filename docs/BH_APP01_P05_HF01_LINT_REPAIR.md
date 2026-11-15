# BH-APP01 P05 HF01 — Android Lint strict fix

## Evidence

- Exact failed source SHA: `3ea4edf9888057f3340c42ab6039ee00d4d27e79` on PR #19.
- Run [43641875820](https://github.com/Mikeyphw/bindhosts/actions/runs/43641875820), Android job `132591038938`.
- Source job **PASS**; `assembleDebug` **PASS**, `testDebugUnitTest` **NO-SOURCE**, `lintDebug` **FAIL** (one error and eight warnings).
- `UpdateTileService.java:55`: Lint `StartActivityAndCollapseDeprecated` flags the old `startActivityAndCollapse(Intent)` path.

## Repair

- Keep API 34+ on `startActivityAndCollapse(PendingIntent)`.
- For API 26–33 only, call the legacy `Intent` overload through a dedicated, precisely annotated `launchLegacy(Intent)` helper. Do not disable the global Lint gate, baseline the issue, or suppress the whole class.
- Add a regression test that checks the API split, narrow annotation, single deprecated call, update-confirmation intent, and enabled CI `:app:lintDebug`.
- No changes to the hosts/TrackerGuard backend, WebUI, root operations, app signing, or physical-device state.

## Qualification

Source tests and synthetic Git transactions can run on Termux. Android Gradle **only** runs in GitHub Actions. Hosted success and uploaded APK require a new exact-head run after applying HF01. Physical Android 16 acceptance and personal release remain **NOT qualified**.
