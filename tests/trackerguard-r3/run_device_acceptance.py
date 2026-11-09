#!/usr/bin/env python3
"""TrackerGuard R3 dedicated APK lifecycle/IFW acceptance. Opt-in; Android only.

No unrelated apps are enrolled, no existing IFW rules are removed. Requires a
freshly installed isolated lab APK for test execution, with two version codes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

PKG = "com.mikeyphw.trackerguard.ifwlab"
CLASS = PKG + ".ProbeReceiver"
ACTION = PKG + ".PROBE"
MODDIR = "/data/adb/modules/bindhosts"
TRACKER = MODDIR + "/trackerguard.sh"
SIGNATURES = MODDIR + "/data/r3-lab-signatures.tsv"
STATE = "/data/adb/bindhosts/trackerguard"
RULE = f"{PKG}|receiver|{CLASS}"
STATE_FILES = ("rules.tsv", "auto.tsv", "enrolled.tsv", "excluded.tsv")
SERIAL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")

class Refused(RuntimeError):
    pass

class ADB:
    def __init__(self, serial: str, timeout: int = 35):
        if not SERIAL_RE.fullmatch(serial):
            raise Refused("unsafe ADB serial")
        self.serial = serial
        self.timeout = timeout

    def run(self, *args: str, fail: bool = True, timeout: int | None = None) -> str:
        try:
            proc = subprocess.run(["adb", "-s", self.serial, *args], capture_output=True,
                                  text=True, timeout=timeout or self.timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired) as err:
            raise Refused(f"ADB command unavailable or timed out: {err.__class__.__name__}") from err
        output = (proc.stdout or "").replace("\r", "")
        if proc.returncode and fail:
            tail = (proc.stderr or output).strip()[-350:]
            raise Refused(f"ADB command failed ({proc.returncode}): {tail}")
        return output

    def shell(self, *args: str, fail: bool = True) -> str:
        return self.run("shell", *args, fail=fail)

    def root(self, command: str, fail: bool = True) -> str:
        return self.shell("su", "-c", command, fail=fail)

    def tracker(self, *args: str) -> str:
        if not args or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in args):
            raise Refused("unexpected tracker argument")
        # Fixed, test-only signatures. Never modify the production signature DB.
        return self.root("TG_R1_SIGNATURES=" + SIGNATURES +
                         " TG_R2_NO_WATCH_START=1 sh " + TRACKER + " " + " ".join(args))

    def installed(self) -> bool:
        names = self.shell("pm", "list", "packages", "-3")
        return "package:" + PKG in names.splitlines()

    def state_bytes(self) -> dict[str, bytes]:
        result = {}
        for name in STATE_FILES:
            path = STATE + "/" + name
            # Base64 avoids transforming bytes in the adb shell transport.
            output = self.root("test -f " + path + " && base64 " + path)
            import base64
            try:
                result[name] = base64.b64decode(output, validate=False)
            except (ValueError, base64.binascii.Error) as err:
                raise Refused("could not snapshot private rule state") from err
        return result

    def event_received(self, token: str) -> bool:
        output = self.shell("run-as", PKG, "cat", "files/received-events.log", fail=False)
        return token in output.splitlines()

    def probe(self, token: str, expected: bool) -> None:
        self.shell("am", "broadcast", "--user", "0", "--receiver-foreground", "-n",
                   f"{PKG}/{CLASS}", "-a", ACTION, "--es", "token", token, fail=False)
        for _ in range(7):
            received = self.event_received(token)
            if received == expected:
                if not expected:
                    # Give asynchronous delivery time to expose a false block.
                    time.sleep(2)
                    if self.event_received(token):
                        break
                else:
                    return
                if not self.event_received(token):
                    return
            time.sleep(1)
        raise Refused("R3_IFW_ENFORCEMENT_FAILED: " + ("receiver never ran" if expected else "blocked receiver ran"))

    def has_auto(self) -> bool:
        return RULE in self.root("cat " + STATE + "/auto.tsv").splitlines()

    def has_rule(self) -> bool:
        return RULE in self.root("cat " + STATE + "/rules.tsv").splitlines()

    def has_lab_observation(self) -> bool:
        # The monitor is expected to advance its observed-package snapshot;
        # after the final prune, the isolated test app must NOT remain in it.
        return any(row.split("|", 1)[0] == PKG for row in
                   self.root("cat " + STATE + "/seen.tsv").splitlines())


def inspect(adb: ADB) -> None:
    adb.run("get-state")
    if adb.root("id -u").strip() != "0":
        raise Refused("root access not available")
    api = adb.shell("getprop", "ro.build.version.sdk").strip()
    abi = adb.shell("getprop", "ro.product.cpu.abi").strip()
    module = adb.root("test -f " + TRACKER + " && test -r " + SIGNATURES + " && echo ready").strip()
    if module != "ready":
        raise Refused("R3 module or dedicated lab signature not installed")
    report = {"api": api, "abi": abi, "module": "ready", "mode": "inspection-only",
              "lab_installed": adb.installed()}
    print("TG_R3_READ_ONLY_INSPECTION_PASS " + json.dumps(report, sort_keys=True), flush=True)


def validate_lab_apk(apk: Path, version: int) -> None:
    # The live harness refuses to install an arbitrary APK even when its file
    # name looks right. Host BuildTools aapt is required before any device write.
    aapt = shutil.which("aapt")
    if not aapt:
        raise Refused("aapt is required to verify lab APK identity before installation")
    try:
        info = subprocess.run([aapt, "dump", "badging", str(apk)], capture_output=True,
                              text=True, timeout=20, check=True).stdout
        permissions = subprocess.run([aapt, "dump", "permissions", str(apk)],
                                     capture_output=True, text=True, timeout=20, check=True).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        raise Refused("cannot verify lab APK metadata; refusing installation") from err
    match = re.search(r"^package: name='([^']+)' versionCode='([^']+)'", info, re.M)
    if not match or match.group(1) != PKG or match.group(2) != str(version):
        raise Refused("unexpected lab package or version; refusing installation")
    if "uses-permission:" in permissions or "uses-permission:" in info:
        raise Refused("unexpected lab permission; refusing installation")


def acceptance(adb: ADB, apk1: Path, apk2: Path) -> None:
    for p in (apk1, apk2):
        if not p.is_file() or p.stat().st_size < 1024 or not p.name.endswith(".apk"):
            raise Refused("missing or invalid lab APK: " + p.name)
    if hashlib.sha256(apk1.read_bytes()).digest() == hashlib.sha256(apk2.read_bytes()).digest():
        raise Refused("v1 and v2 APKs are identical; cannot qualify update lifecycle")
    validate_lab_apk(apk1, 1)
    validate_lab_apk(apk2, 2)
    inspect(adb)
    if adb.shell("getprop", "ro.build.version.sdk").strip() != "36":
        raise Refused("live R3 qualification requires Android 16 (API 36)")
    if adb.installed():
        raise Refused("lab package already installed; refusing to overwrite user test data")
    # R2 JSON status initializes state, but this only happens after the explicit
    # device-writes flag and after validating that no lab APK is present.
    st = json.loads(adb.tracker("json", "status"))
    if st.get("monitor_enabled") or st.get("enrolled") or st.get("auto_rules"):
        raise Refused("monitor/enrolled/auto state not empty; refuse concurrent R3 experiment")
    if PKG in st.get("excluded", []):
        raise Refused("lab package excluded; existing exclusion must not be changed")
    before = adb.state_bytes()
    if RULE.encode() in before["rules.tsv"] or RULE.encode() in before["auto.tsv"]:
        raise Refused("lab IFW rule pre-exists; refusing to overwrite it")
    installed = False
    enrolled = False
    monitored = False
    baseline_seeded = False
    errors: list[str] = []
    try:
        adb.run("install", "-r", str(apk1), timeout=120)
        installed = True
        adb.shell("am", "start", "-W", "-n", PKG + "/.MainActivity")
        stamp = f"{os.getpid()}_{int(time.time())}"
        adb.probe("R3_BEFORE_" + stamp, True)
        print("TG_R3_BASELINE_DELIVERY_PASS", flush=True)
        # R2 suppresses install/update events during its very first package
        # snapshot. Seed v1 BEFORE installing v2, or the later 'updated'
        # assertion would falsely fail even for correct R2 reconciliation.
        baseline = adb.tracker("monitor", "once")
        if "R2_MONITOR_ONCE_PASS" not in baseline:
            raise Refused("R3_BASELINE_SNAPSHOT_FAILED")
        baseline_seeded = True
        print("TG_R3_BASELINE_SNAPSHOT_PASS", flush=True)
        # Mark ownership before each potentially partially successful command,
        # so cleanup is attempted even if a backend reports failure late.
        monitored = True
        adb.tracker("monitor", "enable")
        enrolled = True
        adb.tracker("enroll", PKG)
        if not adb.has_auto() or not adb.has_rule():
            raise Refused("R3_AUTO_OWNER_MISSING: lab receiver not auto-managed")
        time.sleep(3)
        adb.probe("R3_BLOCK_" + stamp, False)
        print("TG_R3_AUTO_IFW_BLOCK_PASS", flush=True)
        adb.run("install", "-r", str(apk2), timeout=120)
        observed = adb.tracker("monitor", "once")
        if f"R2_OBSERVED: updated {PKG}" not in observed or not adb.has_auto():
            raise Refused("R3_UPDATE_RECONCILIATION_FAILED")
        adb.probe("R3_UPDATED_BLOCK_" + stamp, False)
        print("TG_R3_PACKAGE_UPDATE_PASS", flush=True)
        print("TG_R3_UPDATED_IFW_BLOCK_PASS", flush=True)
        adb.run("uninstall", PKG, timeout=120)
        installed = False
        adb.tracker("monitor", "once")
        if adb.has_auto() or adb.has_rule():
            raise Refused("R3_UNINSTALL_AUTO_PRUNE_FAILED")
        print("TG_R3_UNINSTALL_PRUNE_PASS", flush=True)
        adb.run("install", "-r", str(apk2), timeout=120)
        installed = True
        adb.shell("am", "start", "-W", "-n", PKG + "/.MainActivity")
        adb.tracker("monitor", "once")
        if not adb.has_auto() or not adb.has_rule():
            raise Refused("R3_REINSTALL_RECONCILIATION_FAILED")
        time.sleep(3)
        adb.probe("R3_REINSTALLED_BLOCK_" + stamp, False)
        print("TG_R3_REINSTALL_AUTO_BLOCK_PASS", flush=True)
        # The final live phase must prove that unenrolling restores delivery,
        # not just that a row disappeared from the private IFW rules database.
        adb.tracker("unenroll", PKG)
        enrolled = False
        time.sleep(3)
        adb.probe("R3_AFTER_UNENROLL_" + stamp, True)
        print("TG_R3_IFW_ROLLBACK_DELIVERY_PASS", flush=True)
    finally:
        # Every cleanup action is independent, even after a failed test step.
        # Never bulk-restore other apps or act on unrelated packages.
        if enrolled:
            try: adb.tracker("unenroll", PKG)
            except Refused as e: errors.append("unenroll: " + str(e))
        if monitored:
            try: adb.tracker("monitor", "disable")
            except Refused as e: errors.append("monitor-disable: " + str(e))
        try:
            if installed or adb.installed():
                adb.run("uninstall", PKG, timeout=120)
        except Refused as e:
            errors.append("uninstall: " + str(e))
        # Do not retry cleanup snapshot if initial snapshot never succeeded.
        if baseline_seeded:
            try: adb.tracker("monitor", "once")
            except Refused as e: errors.append("reconcile: " + str(e))
        try:
            after = adb.state_bytes()
            for name in STATE_FILES:
                if before[name] != after[name]:
                    errors.append("private state differs after cleanup: " + name)
            # seen.tsv and monitor.log are operational observation history,
            # not rollback snapshots. Verify no lab package survives in seen.
            if adb.has_lab_observation():
                errors.append("lab package remains in observer seen.tsv")
        except Refused as e:
            errors.append("verify: " + str(e))
        if errors:
            print("TG_R3_CLEANUP_FAILED " + "; ".join(errors), file=sys.stderr, flush=True)
            raise Refused("R3 cleanup incomplete; inspect TrackerGuard before further changes")
        print("TG_R3_CLEANUP_PASS: original rules and monitoring state retained", flush=True)
    print("TG_R3_LIVE_ACCEPTANCE_PASS", flush=True)


def main() -> int:
    def interrupt(signum, _frame):
        raise Refused(f"interrupted by signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    p = argparse.ArgumentParser(description="TrackerGuard R3 isolated Android 16 lifecycle acceptance")
    p.add_argument("--serial", default="localhost:5555")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--read-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    p.add_argument("--apk-v1", type=Path)
    p.add_argument("--apk-v2", type=Path)
    p.add_argument("--accept-device-writes", action="store_true")
    args = p.parse_args()
    try:
        adb = ADB(args.serial)
        if args.read_only:
            if args.accept_device_writes or args.apk_v1 or args.apk_v2:
                raise Refused("read-only mode cannot include write flags or APK inputs")
            inspect(adb)
        else:
            if not args.accept_device_writes or not args.apk_v1 or not args.apk_v2:
                raise Refused("--run requires both APKs and --accept-device-writes")
            acceptance(adb, args.apk_v1, args.apk_v2)
        return 0
    except Refused as e:
        print("TG_R3_REFUSED: " + str(e), file=sys.stderr, flush=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
