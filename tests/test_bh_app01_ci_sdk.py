#!/usr/bin/env python3
"""HF03 SDK bootstrap regression and failure diagnostics, no Android SDK needed."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/bh_app01_android_sdk.sh"
WORKFLOW = ROOT / ".github/workflows/bh-app01-foundation.yml"


class AndroidSdkBootstrap(unittest.TestCase):
    def test_no_obsolete_setup_action_or_tools_package(self):
        source = WORKFLOW.read_text()
        self.assertNotIn("android-actions/setup-android@v3", source)
        self.assertNotIn("sdkmanager tools", source)
        self.assertIn("bash scripts/ci/bh_app01_android_sdk.sh", source)
        self.assertIn("gradle/actions/setup-gradle@v4", source)
        self.assertIn("assembleDebug :app:testDebugUnitTest", source)
        self.assertIn("if-no-files-found: error", source)

    def invoke(self, *, mode="success", create_manager=True, manager_name="16.0"):
        with tempfile.TemporaryDirectory(prefix="bh-app01-sdk-") as t:
            root = Path(t) / "android-sdk"
            bin_dir = root / "cmdline-tools" / manager_name / "bin"
            bin_dir.mkdir(parents=True)
            capture = Path(t) / "sdk-args.txt"
            if create_manager:
                fake = bin_dir / "sdkmanager"
                fake.write_text('''#!/usr/bin/env bash
printf '%s\n' "$@" > "$BH_APP01_TEST_CAPTURE"
if [[ "$BH_APP01_TEST_MODE" == "failed" ]]; then exit 41; fi
if [[ "$BH_APP01_TEST_MODE" == "license_failed" && " $* " == *" --licenses "* ]]; then exit 42; fi
if [[ "$BH_APP01_TEST_MODE" != "missing_outputs" && " $* " != *" --licenses "* ]]; then
 mkdir -p "$ANDROID_HOME/platforms/android-36" "$ANDROID_HOME/build-tools/36.0.0"
 : > "$ANDROID_HOME/platforms/android-36/android.jar"
 : > "$ANDROID_HOME/build-tools/36.0.0/aapt2"
 chmod +x "$ANDROID_HOME/build-tools/36.0.0/aapt2"
fi
''')
                fake.chmod(0o755)
            env = {**os.environ, "ANDROID_HOME": str(root), "ANDROID_SDK_ROOT": str(root),
                   "BH_APP01_TEST_CAPTURE": str(capture), "BH_APP01_TEST_MODE": mode}
            result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env, timeout=15)
            args = capture.read_text().splitlines() if capture.exists() else []
            return result, args

    def test_success_installs_only_supported_packages_and_readback(self):
        result, args = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[-3:], ["--install", "platforms;android-36", "build-tools;36.0.0"])
        self.assertTrue(args[0].startswith("--sdk_root="))
        self.assertIn("BH_APP01_ANDROID_SDK36_READY", result.stdout)

    def test_missing_tools_fail_closed(self):
        result, _ = self.invoke(create_manager=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no executable sdkmanager", result.stderr)

    def test_license_failure_fails_closed(self):
        result, _ = self.invoke(mode="license_failed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SDK license acceptance failed", result.stderr)
        self.assertNotIn("SDK36_READY", result.stdout)

    def test_manager_failure_fails_closed(self):
        result, _ = self.invoke(mode="failed")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SDK36_READY", result.stdout)

    def test_missing_output_files_fail_closed(self):
        result, _ = self.invoke(mode="missing_outputs")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("android.jar missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
