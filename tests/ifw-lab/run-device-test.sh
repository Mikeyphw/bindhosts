#!/bin/sh
# TrackerGuard IFW acceptance on a rooted Android 16 device, via adb shell UID 2000.
# Only the lab package's own IFW receiver rule is ever added/removed.
set -eu

SERIAL=${ADB_SERIAL:-localhost:5555}
APK=${1:-}
PKG=com.mikeyphw.trackerguard.ifwlab
CLASS=com.mikeyphw.trackerguard.ifwlab.ProbeReceiver
ACTION=com.mikeyphw.trackerguard.ifwlab.PROBE
MOD=/data/adb/modules/bindhosts/bindhosts.sh
OWNED=0

note() { printf '%s\n' "$*"; }
adb_cmd() { adb -s "$SERIAL" "$@"; }
adb_shell() { adb_cmd shell "$@"; }
tracker() { adb_shell su -c "sh $MOD tracker $*"; }
cleanup() {
    if [ "$OWNED" = 1 ]; then
        note '=== SAFETY ROLLBACK: remove lab-only IFW rule ==='
        tracker remove "$PKG" receiver "$CLASS" || note 'TG_IFW_LAB_ROLLBACK_FAILED: check tracker list and restore lab rule manually'
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[ -n "$APK" ] && [ -s "$APK" ] || {
    note 'Usage: sh run-device-test.sh /path/to/app-debug.apk'
    exit 2
}
command -v adb >/dev/null 2>&1 || { note 'ADB_NOT_FOUND'; exit 2; }
adb_cmd get-state | grep -Fxq device || { note "ADB_DEVICE_UNAVAILABLE: $SERIAL"; exit 2; }
SDK=$(adb_shell getprop ro.build.version.sdk | tr -d '\r')
ABI=$(adb_shell getprop ro.product.cpu.abi | tr -d '\r')
note "Device: Android API $SDK, ABI $ABI, ADB $SERIAL"
[ "$SDK" = 36 ] || note 'Warning: test planned for Android 16 (API 36).'

note '=== Install isolated, no-network test APK ==='
adb_cmd install -r "$APK"
# Opening once clears package-stopped state on a freshly installed app.
adb_shell am start -W -n "$PKG/.MainActivity"
adb_shell run-as "$PKG" pwd >/dev/null || { note 'RUN_AS_FAILED: expected debuggable test APK'; exit 2; }
adb_shell su -c 'pm list packages -3' | tr -d '\r' | grep -Fxq "package:$PKG" || {
    note 'LAB_PACKAGE_NOT_A_USER_APP'; exit 2;
}

note '=== Preserve existing rules ==='
INITIAL_RULES=$(tracker list)
if printf '%s\n' "$INITIAL_RULES" | grep -Fq "$PKG|"; then
    note 'LAB_RULE_ALREADY_PRESENT: refusing to change an existing rule'
    exit 2
fi
printf '%s\n' "$INITIAL_RULES"

was_received() {
    # run-as reads *app-private* evidence, not the broadcast command's result.
    adb_shell run-as "$PKG" cat files/received-events.log 2>/dev/null |
        tr -d '\r' | grep -Fxq "$1"
}
wait_received() {
    _token=$1
    _attempt=0
    while [ "$_attempt" -lt 10 ]; do
        was_received "$_token" && return 0
        _attempt=$((_attempt + 1))
        sleep 1
    done
    return 1
}
send_probe() {
    _token=$1
    # Normal adb shell UID, not root, invokes ActivityManager. Action matches manifest.
    adb_shell am broadcast --user 0 --receiver-foreground \
        -n "$PKG/$CLASS" -a "$ACTION" --es token "$_token"
}

STAMP="$(date +%s)_$$"
BEFORE="TG_BEFORE_$STAMP"
BLOCKED="TG_BLOCKED_$STAMP"
AFTER="TG_AFTER_$STAMP"

note '=== Baseline: receiver MUST execute before IFW block ==='
send_probe "$BEFORE"
if ! wait_received "$BEFORE"; then
    note 'TG_IFW_LAB_BASELINE_FAILED: receiver not invoked even before blocking'
    note 'Check adb shell run-as, package receiver export, and Android broadcast warnings.'
    exit 1
fi
note 'TG_IFW_LAB_BASELINE_PASS: private receiver record observed'

note '=== Block only dedicated lab receiver using TrackerGuard ==='
OWNED=1
if ! tracker add "$PKG" receiver "$CLASS"; then
    note 'TG_IFW_LAB_ADD_FAILED; cleanup will attempt lab-only rollback'
    exit 1
fi
tracker list | grep -Fxq "$PKG|receiver|$CLASS" || {
    note 'TG_IFW_LAB_RULE_NOT_PERSISTED'; exit 1;
}
adb_shell su -c 'ls -lZ /data/system/ifw/bindhosts_trackerguard.xml'
sleep 3

note '=== While blocked: receiver MUST NOT record delivery ==='
# Some Android builds report a nonzero exit on denial; it is not the proof.
send_probe "$BLOCKED" || note 'BROADCAST_RETURNED_NONZERO_WHILE_BLOCKED'
sleep 5
if was_received "$BLOCKED"; then
    note 'TG_IFW_LAB_BLOCK_FAILED: blocked receiver actually ran'
    exit 1
fi
note 'TG_IFW_LAB_BLOCK_PASS: no receiver execution observed'

note '=== Remove only the lab rule; keep every unrelated rule ==='
if ! tracker remove "$PKG" receiver "$CLASS"; then
    note 'TG_IFW_LAB_REMOVE_FAILED; cleanup will retry'
    exit 1
fi
tracker list | grep -Fxq "$PKG|receiver|$CLASS" && {
    note 'TG_IFW_LAB_RULE_STILL_PRESENT'; exit 1;
}
OWNED=0
sleep 3

note '=== After rollback: receiver MUST execute again ==='
send_probe "$AFTER"
if ! wait_received "$AFTER"; then
    note 'TG_IFW_LAB_RESTORE_FAILED: receiver not invoked after rollback'
    exit 1
fi
note 'TG_IFW_LAB_RESTORE_PASS: private receiver record observed'

FINAL_RULES=$(tracker list)
[ "$FINAL_RULES" = "$INITIAL_RULES" ] || {
    note 'TG_IFW_LAB_RULE_JOURNAL_DIFFERS: check for concurrent rule changes'
    note "Before: $INITIAL_RULES"
    note "After: $FINAL_RULES"
    exit 1
}
note 'TG_IFW_LAB_PASS: delivered before, denied while blocked, delivered after rollback; prior rules preserved'
