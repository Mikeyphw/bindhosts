# PH03 extension: module ZIP containing exact hosted-tested companion APK

Source: PR #19 on `feature/bh-app01-p00-p03-companion-foundation-20261114`.
This is an extension of the P07 PH03 physical non-root acceptance overlay.

The `BH-APP01 P07 Module ZIP with Hosted-Tested Companion APK` **pull-request** workflow:

1. Checks out the exact PR HEAD (not the GitHub PR merge commit), refuses drift, and waits for four named required GitHub workflows to pass on this SHA.
2. Downloads the artifact of the passing **P07 Hosted API36 UI Acceptance** run for that exact SHA, including `hosted-app-debug.apk`, full instrumentation and cold-start evidence, and installed-byte SHA-256.
3. Independently reruns `bh_app01_p07_signoff.py` over the real evidence and requires its JSON receipt and both APK checksums to match.
4. Builds the native module scanner/HTTP responder/HTTPS TLS binaries for arm64-v8a, armeabi-v7a and x86_64, plus the original WebUI, in GitHub Actions. **It does not recompile the companion APK**: the embedded APK is the binary that actually passed the emulator.
5. Produces an installable module ZIP with `META-INF`, `module.prop`, native binaries, WebUI, module scripts and `companion/bindhosts-companion.apk`. It embeds the full commit SHA, exact APK SHA-256 and an explicit `release_qualified: false`-equivalent receipt.
6. Uploads `bh-app01-module-companion-<full-SHA>` as a workflow artifact. Download it from the workflow run's Artifacts section, then extract the **inner** `bindhosts-P07-companion-<full-SHA>.zip` for installation in KernelSU/APatch/Magisk. The GitHub Actions artifact wrapper is NOT the module to flash.

## Device behavior

When installing the bundled module through the root-manager UI, `customize.sh` attempts to install/update the *bundled* `com.mikeyphw.bindhosts` APK offline. It confirms its hash before passing it to PackageManager and verifies the installed package hash afterwards. If the exact APK is already installed, it skips reinstalling it. **No network download of the legacy BindHosts app is made**, no root permission is automatically granted to the companion, and an existing app is never uninstalled or wiped to bypass a signature/version conflict. If the app install is refused, the module installation continues and prints a visible warning: inspect the installer output; do not assume the app was installed.

The debug APK is source-bound and Android-emulator-tested, **not** a signed personal release or physically tested production app. Android may reject an update if a previously installed companion was signed with a different debug certificate. An uninstall is never performed automatically and may erase app data if later chosen manually.

No physical Android device is written during GitHub packaging; physical PH03 acceptance, SAF imports, TrackerGuard/IFW writes, hosts restoration, and P08 personal signing remain separate gates. Android Gradle builds remain hosted only.
