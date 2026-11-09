# TrackerGuard R1 HF04 — KernelSU native executable permissions

## Device finding

Android 16 / SDK 36 / arm64-v8a / KernelSU installed the `axmlscan` native scanner with
`-rw-r--r--` (0644) even though the GitHub Actions build gave it 0755. The root CLI
therefore returned `scanner missing for arm64-v8a`, although the file existed.
The original bindhosts installation script only restored permissions for shell wrappers.

KernelSU's default installer applies 0644 permissions to ordinary module files. Its
`customize.sh` is sourced *after* default permissions, with `set_perm` available.
The portable solution is to call `set_perm` on each of the packaged native scanners.

## Fix

- Set each scanner (arm64-v8a, armeabi-v7a, x86_64) to 0755 during module install.
- Abort installation if an expected scanner is missing or not executable.
- Keep shell wrapper / hosts / WebUI behavior unchanged.
- Add an isolated installer regression that starts with the KernelSU-default 0644,
  checks all three ABIs, and validates failure for a missing ABI.
- Bump module version to v2.1.5-tg.0.3 (21603) without enabling automatic release.

## Immediate on-device recovery (no new ZIP needed)

```sh
su -c 'chmod 0755 /data/adb/modules/bindhosts/bin/arm64-v8a/axmlscan'
su -c 'sh /data/adb/modules/bindhosts/bindhosts.sh tracker preview org.futo.inputmethod.latin'
```

Do **not** assume the scanner or IFW enforcement works until the on-device preview and
controlled IFW runtime tests pass. The installer fix is permanent for future installs;
existing R1 installations still need the one-time chmod or an upgraded module ZIP.

Do not run the `block` command on a system app or use automatic bulk blocking during
this qualification stage.
