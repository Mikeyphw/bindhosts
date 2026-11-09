#!/bin/sh
# Only remove our own IFW rules; never touch App Manager's rules.
tg_ifw=/data/system/ifw/bindhosts_trackerguard.xml
if [ -f "$tg_ifw" ] && [ ! -L "$tg_ifw" ] && grep -Fq '<!-- bindhosts-tracker: managed IFW file -->' "$tg_ifw"; then
    rm -f "$tg_ifw"
fi
# Stop only our own loopback HTTP responder before removing persistent state.
if [ -f /data/adb/modules/bindhosts/response_mode.sh ]; then
    sh /data/adb/modules/bindhosts/response_mode.sh /data/adb/bindhosts \
      /data/adb/modules/bindhosts/system/etc/hosts stop >/dev/null 2>&1 || :
fi
# Never destroy the only valid preimage after a crash in an in-place write.
_bh_discard_state=1
if [ -e /data/adb/bindhosts/.hosts-target-journal ]; then
    _bh_discard_state=0
    _bh_target_file=/data/adb/bindhosts/.hosts-target-journal/target
    if [ -f "$_bh_target_file" ] && [ ! -L "$_bh_target_file" ]; then
        _bh_recover_target=$(cat "$_bh_target_file")
        if sh /data/adb/modules/bindhosts/hosts_target_safe.sh recover "$_bh_recover_target"; then
            _bh_discard_state=1
        else
            echo 'BH_UNINSTALL_JOURNAL_PRESERVED: manual recovery required' >&2
        fi
    else
        echo 'BH_UNINSTALL_JOURNAL_PRESERVED: incomplete recovery metadata' >&2
    fi
fi
# delete settings
[ "$_bh_discard_state" = 1 ] && rm -rf /data/adb/bindhosts
# delete symlink, ap/ksu
rm /data/adb/ap/bin/bindhosts 
rm /data/adb/ksu/bin/bindhosts
# cleanup for helper modes
# hfr
[ -f /data/adb/hosts ] && printf "127.0.0.1 localhost\n::1 localhost\n" > /data/adb/hosts
# znhr
[ -f /data/adb/hostsredirect/hosts ] && printf "127.0.0.1 localhost\n::1 localhost\n" > /data/adb/hostsredirect/hosts

# uninstall bindhosts app if installed
pm path "$APP_PACKAGE" > /dev/null 2>&1 && pm uninstall me.itejo443.bindhosts

# EOF
