# BH-APP01 HF04 — TileService main-looper compilation repair

## Verified hosted failure

GitHub Actions run 43616489318, `android` job 132512598883, commit
`c590ec762dc230a30029ae0a9c14e3ce49daadb4`:

* Source tests and Android SDK 36 setup passed.
* `:app:compileDebugJavaWithJavac` failed because `ProtectionTileService`, a
  `TileService` (not an `Activity`), called undefined `runOnUiThread(...)`.
* `app-debug.apk` was not generated and no physical Android acceptance occurred.

## Repair

Use `Handler(Looper.getMainLooper()).post(...)` to deliver the verified tile
state from the background root reader to the UI thread. Drop pending callbacks
in `onDestroy()` and prevent a late worker response from updating a destroyed
service. Keep tile actions status-only; no hosts/TrackerGuard modifications.

The source-contract suite now rejects `runOnUiThread` in `TileService` and
requires main-looper posting plus teardown cancellation. Kotlin/Java Android
compilation still **must** run in GitHub Actions and provide a build artifact
for the exact new commit. No local Gradle or root/device writes are performed.

## HF04 security and release gates

* Verify PR #19 remains stacked on UX10 PR #18.
* Preserve the original branch and all HF03 files except the two source paths.
* Require a verified single-parent commit based on the exact HF03 SHA.
* Run source tests before committing; on failure restore only HF04-owned files.
* Discover and monitor actual GitHub Actions runs by exact head SHA.
* No release or physical acceptance claim without a successful hosted Android
  job, artifact checksum, and separate device checks.
