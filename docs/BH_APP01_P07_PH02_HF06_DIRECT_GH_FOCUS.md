# BH-APP01 P07 PH02 HF06 — Native QS focus + direct GH terminal output

Parent PR #19 commit: `65af1effaa7d410cf27a7dad75294550beeafc07`.

## Failure

P07 hosted API36 test failed in both PR run `43674480323` and push run `43674476195` with Espresso `RootViewWithoutFocusException`. The background `BASE_APPLICATION` window loses focus when the actual AlertDialog is shown. The previous source used `onView(withText(...))`, which may select that background root.

## Fix

The live instrumentation test now locates the native AlertDialog through the companion's own `updateConfirmation` field. It verifies the dialog is visible, checks the actual title and the negative/positive buttons, invokes the real Cancel button's `performClick()` on the main thread, and verifies dismissal and preserved Activity/WebView. It never invokes Update. The **independent** API36 ADB cold-start/UIAutomator test remains mandatory, including the real touchscreen Cancel tap, native event audit and APK SHA-256 verification.

The Termux overlay launcher now calls `gh run watch <id> --repo Mikeyphw/bindhosts --exit-status` for **every source-matched workflow run, including completed runs**, with inherited stdout/stderr (actual CLI text and ANSI/TUI output). It then calls `gh pr checks 19 --repo Mikeyphw/bindhosts` with inherited stdout/stderr. All underlying calls are printed, unfiltered, and never replace actual CLI output with fabricated status strings. Exit codes and exact-SHA JSON verification remain mandatory; `gh run view --log-failed` still captures failed run logs.

There is no local Gradle, no automatic device access, no force push, no merge, and no release qualification. If `gh run list` cannot discover a new required workflow yet, the launcher prints actual `gh pr checks` output and reports pending discovery, with `--resume` supported.

## Usage

```zsh
python3 /sdcard/Download/BH_APP01_P07_PH02_HF06_GH_DIRECT_FOCUS_REPAIR_CONSOLIDATED.zip --test
python3 /sdcard/Download/BH_APP01_P07_PH02_HF06_GH_DIRECT_FOCUS_REPAIR_CONSOLIDATED.zip --apply --publish --root "$HOME/Code/bindhosts"
python3 /sdcard/Download/BH_APP01_P07_PH02_HF06_GH_DIRECT_FOCUS_REPAIR_CONSOLIDATED.zip --resume --root "$HOME/Code/bindhosts"
```

`--test` uses disposable local mocks only. No physical writes are performed. Hosted qualification is pending a fresh GH Actions run at the new source SHA.
