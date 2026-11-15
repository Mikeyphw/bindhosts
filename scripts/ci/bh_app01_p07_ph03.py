#!/usr/bin/env python3
"""BH-APP01 P07 PH03: source-qualified Android 16 non-root UI journeys.

All device interactions are explicit, limited to the pinned localhost:5555 device,
and refused unless a user supplies the exact UI-authorization phrase. No
installation, root access, hosts writes, IFW writes, data clearing, file pick,
or changes to Android settings. Raw hierarchies are never saved locally.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import bh_app01_p07_ph02 as ph02
from bh_app01_p07_physical_v2 import inspect as physical_inspect, write_private

APP = 'com.mikeyphw.bindhosts'
SERIAL = 'localhost:5555'
ACK = 'I_AUTHORIZE_PH03_NONROOT_UI_ACTIONS'
READ_ACK = 'I_AUTHORIZE_READ_ONLY_DEVICE_PROBE'
MAX_XML = 1_000_000
NODE_BOUNDS = re.compile(r'\[(\d{1,5}),(\d{1,5})\]\[(\d{1,5}),(\d{1,5})\]\Z')
NONCE = re.compile(r'[0-9a-f]{16}\Z')
APP_COMPONENT = APP + '/.MainActivity'
QS_ACTION = APP + '.CONFIRM_UPDATE'
PICKER_PACKAGES = ('com.google.android.documentsui', 'com.android.documentsui')
TAB_LABELS = {'rules': ('Rules',), 'apps': ('Apps',), 'more': ('More',),
              'home': ('Home','Início','Inicio')}
TAB_MARKERS = {'rules': ('Blocking controls',), 'apps': ('TrackerGuard',),
               'more': ('Activity & diagnostics', 'Activity and diagnostics'),
               'home': ('App tracker protection',)}

class Refused(ph02.Refused):
    pass

def refuse(message):
    raise Refused(message)


def temp_path(nonce):
    if not NONCE.fullmatch(nonce):refuse('INVALID_OWN_TEMP_NONCE')
    return '/sdcard/Download/.bh-app01-ph03-' + nonce + '.xml'


def validate_command(parts, path):
    """Never permit an arbitrary ADB argv, shell script, or filesystem path."""
    allowed = {
        ('get-state',),
        ('shell','getprop','ro.build.version.sdk'),
        ('shell','getprop','ro.product.cpu.abi'),
        ('shell','getprop','ro.kernel.qemu'),
        ('shell','dumpsys','activity','activities'),
        ('shell','am','start','-W','-n',APP_COMPONENT),
        ('shell','am','start','-W','-n',APP_COMPONENT,'-a',QS_ACTION),
        ('shell','input','keyevent','KEYCODE_BACK'),
    }
    command = tuple(parts)
    if command in allowed:return
    if not path or not re.fullmatch(r'/sdcard/Download/\.bh-app01-ph03-[0-9a-f]{16}\.xml',path):
        refuse('INVALID_TEMP_PATH')
    if command in {('shell','uiautomator','dump',path),('exec-out','cat',path),
                   ('shell','test','-e',path),('shell','rm','-f',path)}:return
    # The only touch allowed is the center of a separately parsed UI hierarchy.
    if (len(parts) == 5 and parts[:3] == ['shell','input','tap']
            and all(re.fullmatch(r'[0-9]{1,5}',v) for v in parts[3:])):return
    refuse('ADB_COMMAND_NOT_ALLOWLISTED')


def adb(parts, *, path=None, timeout=22, optional=False, limit=MAX_XML):
    validate_command(parts,path)
    p = subprocess.run(['adb','-s',SERIAL,*parts],capture_output=True,timeout=timeout,check=False)
    if len(p.stdout)>limit or len(p.stderr)>4096:refuse('ADB_RESPONSE_TOO_LARGE')
    if p.returncode and not optional:refuse('ADB_FAILED_'+str(p.returncode)+'_'+parts[0])
    return p


def own_tree(raw):
    if not (50 <= len(raw) <= MAX_XML):refuse('INVALID_XML_LENGTH')
    try:root=ET.fromstring(raw)
    except ET.ParseError as exc:raise Refused('MALFORMED_UI_HIERARCHY') from exc
    if root.tag!='hierarchy':refuse('INVALID_UI_ROOT')
    nodes=list(root.iter('node'))
    if len(nodes)>15000:refuse('TOO_MANY_UI_NODES')
    return nodes


def center(node):
    b=node.get('bounds','')
    match=NODE_BOUNDS.fullmatch(b)
    if not match:refuse('INVALID_UI_BOUNDS')
    x1,y1,x2,y2=map(int,match.groups())
    if not (0<=x1<x2<=8192 and 0<=y1<y2<=8192):refuse('UNSAFE_UI_BOUNDS')
    return (x1+x2)//2,(y1+y2)//2, y2


def screen_extent(nodes):
    bottoms=[]
    for node in nodes:
        m=NODE_BOUNDS.fullmatch(node.get('bounds',''))
        if m: bottoms.append(int(m.group(4)))
    height=max(bottoms or [0])
    if not 500<=height<=8192:refuse('UNKNOWN_SCREEN_EXTENT')
    return height


def label_of(node):
    return (node.get('text') or node.get('content-desc') or '').strip()


def find_nav_tab(nodes,name):
    if name not in TAB_LABELS:refuse('UNSUPPORTED_NAV_TARGET')
    height=screen_extent(nodes)
    matches=[]
    for node in nodes:
        if label_of(node) not in TAB_LABELS[name]:continue
        try:x,y,bottom=center(node)
        except Refused:continue
        if y>height*0.71 and bottom<=height:
            matches.append((x,y))
    if len(matches)!=1:refuse('NAV_TAB_NOT_UNIQUE_'+name)
    return matches[0]


def visible_marker(nodes,name):
    if name not in TAB_MARKERS:refuse('UNSUPPORTED_NAV_TARGET')
    return any(label_of(n) in TAB_MARKERS[name] for n in nodes)


def focused_package(text):
    """Read only explicitly named *currently resumed* Android activities."""
    for line in text.splitlines():
        if not re.search(r'(?:topResumedActivity|mResumedActivity|ResumedActivity|mFocusedApp)\b',line):
            continue
        for package in (APP,*PICKER_PACKAGES):
            if re.search(r'(?<![\w.])'+re.escape(package)+r'(?=/|\b)',line):return package
    return None


def require_target():
    if adb(['get-state']).stdout.strip()!=b'device':refuse('ADB_DEVICE_NOT_READY')
    if adb(['shell','getprop','ro.build.version.sdk']).stdout.strip()!=b'36':refuse('REQUIRES_ANDROID16')
    if adb(['shell','getprop','ro.product.cpu.abi']).stdout.strip()!=b'arm64-v8a':refuse('REQUIRES_ARM64')
    if adb(['shell','getprop','ro.kernel.qemu']).stdout.strip()==b'1':refuse('EMULATOR_REFUSED')


def focus():
    out=adb(['shell','dumpsys','activity','activities'],limit=200000).stdout.decode('utf-8','replace')
    return focused_package(out)


class Session:
    def __init__(self):
        self.path=temp_path(secrets.token_hex(8))
        self.created=False
        self.cleaned=False
    def __enter__(self):
        if adb(['shell','test','-e',self.path],path=self.path,optional=True).returncode==0:
            refuse('OWN_TEMP_FILE_COLLISION')
        return self
    def snapshot(self):
        self.created=True
        adb(['shell','uiautomator','dump',self.path],path=self.path,timeout=28,limit=4096)
        raw=adb(['exec-out','cat',self.path],path=self.path,timeout=18).stdout
        return own_tree(raw),hashlib.sha256(raw).hexdigest()
    def __exit__(self,exc_type,exc,tb):
        if self.created:
            self.cleaned = adb(['shell','rm','-f',self.path],path=self.path,optional=True).returncode==0
            if self.cleaned:
                self.cleaned = adb(['shell','test','-e',self.path],path=self.path,optional=True).returncode!=0
        else:self.cleaned=True
        if not self.cleaned:refuse('OWN_TEMP_CLEANUP_NOT_VERIFIED')


def safe_tap(x,y,s):
    if not (isinstance(x,int) and isinstance(y,int) and 0<x<8192 and 0<y<8192):
        refuse('UNSAFE_TAP_COORDINATES')
    adb(['shell','input','tap',str(x),str(y)],path=s.path,timeout=14,limit=4000)


def wait_marked(s,name,tries=7):
    for i in range(tries):
        nodes,h=s.snapshot()
        if visible_marker(nodes,name):return nodes,h
        if i<tries-1:time.sleep(.7)
    refuse('EXPECTED_PAGE_MARKER_MISSING_'+name)


def start_ui():
    started=adb(['shell','am','start','-W','-n',APP_COMPONENT],limit=6000,timeout=30)
    if b'Status: ok' not in started.stdout:refuse('MAIN_ACTIVITY_LAUNCH_UNVERIFIED')
    for _ in range(10):
        if focus()==APP:return
        time.sleep(.4)
    refuse('MAIN_ACTIVITY_NOT_FOREGROUND')


def navigation_journey():
    require_target()
    start_ui()
    observed={}
    with Session() as s:
        nodes,home_hash=wait_marked(s,'home')
        observed['home']=home_hash
        for tab in ('rules','apps','more','home'):
            # Find and tap only the bottom navigation tab, never an action button.
            x,y=find_nav_tab(nodes,tab)
            safe_tap(x,y,s)
            nodes,digest=wait_marked(s,tab)
            if focus()!=APP:refuse('LEFT_COMPANION_DURING_NAVIGATION')
            observed[tab]=digest
        # Repeated home marker is expected but Rules/Apps/More must differ.
        if len({observed['rules'],observed['apps'],observed['more']}) != 3:
            refuse('NAVIGATION_VIEW_NOT_CHANGED')
    return {'navigation_pages':['home','rules','apps','more','home'],
            'unique_content_views':3,'sanitized_hierarchy_sha256':observed,
            'navigation_completed':True,'device_temp_xml_cleanup':True}


def saf_cancel_journey(*,timeout_seconds=95):
    """User opens the app's real SAF picker. Never select any document."""
    require_target();start_ui()
    print('PH03 SAF: On the phone, open Rules, find the custom .txt import, and tap Import/Open file. DO NOT select a file. The suite will detect Android DocumentsUI and press Back.')
    started=time.monotonic()
    observed=False
    while time.monotonic()-started<timeout_seconds:
        if focus() in PICKER_PACKAGES:
            observed=True;break
        time.sleep(.9)
    if not observed:refuse('REAL_DOCUMENTS_PICKER_NOT_OBSERVED')
    adb(['shell','input','keyevent','KEYCODE_BACK'],timeout=12,limit=2000)
    returned=False
    for _ in range(12):
        if focus()==APP:returned=True;break
        time.sleep(.5)
    if not returned:refuse('COMPANION_NOT_RESUMED_AFTER_SAF_CANCEL')
    return {'saf_picker_seen':True,'saf_picker_cancelled':True,
            'document_opened':False,'file_imported':False,'saf_full_import_qualified':False}


def qs_duplicate_cancel_journey():
    """Duplicate real QS intents while dialog is visible; tap only Cancel."""
    require_target()
    started=[]
    with Session() as s:
        for _ in range(2):
            p=adb(['shell','am','start','-W','-n',APP_COMPONENT,'-a',QS_ACTION],timeout=30,limit=8000)
            if b'Status: ok' not in p.stdout:refuse('QS_INTENT_LAUNCH_UNVERIFIED')
            started.append(hashlib.sha256(p.stdout).hexdigest())
        xy=None;before=None
        for _ in range(12):
            nodes,digest=s.snapshot()
            try:
                # The existing parser checks real dialog title and exactly one clickable Cancel.
                from bh_app01_p07_qs_hierarchy import parse as parse_qs
                with tempfile.TemporaryDirectory(prefix='bh-ph03-parse-') as td:
                    # Only synthetic temp files on the host; no persistent raw UI.
                    p=Path(td)/'dialog.xml'
                    # Read our one owned on-device file, already hashed and size checked.
                    raw=adb(['exec-out','cat',s.path],path=s.path).stdout
                    p.write_bytes(raw)
                    xy=parse_qs(p)
                before=digest;break
            except (ValueError,ET.ParseError):time.sleep(.6)
        if xy is None:refuse('DUPLICATE_QS_DIALOG_NOT_VISIBLE')
        safe_tap(xy[0],xy[1],s)
        for _ in range(12):
            nodes,_=s.snapshot()
            if not any(label_of(n)=='Update Bindhosts rules?' for n in nodes):break
            time.sleep(.6)
        else:refuse('QS_DIALOG_REMAINED_AFTER_CANCEL')
        if focus()!=APP:refuse('QS_CANCEL_LEFT_APPLICATION')
        # Give queued/misdelivered duplicate intent a chance to re-show itself.
        time.sleep(1)
        nodes,_=s.snapshot()
        if any(label_of(n)=='Update Bindhosts rules?' for n in nodes):
            refuse('DUPLICATE_QS_DIALOG_REAPPEARED')
    return {'qs_intents_delivered':2,'only_cancel_tapped':True,
            'duplicate_confirmation_not_left_open':True,
            'qs_confirmation_hierarchy_sha256':before,
            'qs_launch_response_sha256':started,'device_temp_xml_cleanup':True,
            'hosts_update_triggered_by_runner':False}


def checked_context(root,sha,out):
    proof=ph02.verified_hosted(root,sha,out)
    hosted=Path(out)/'hosted-receipt.json'
    physical=physical_inspect(SERIAL,sha,hosted)
    if not physical['hosted_apk_matches_installed'] or physical['read_only_status']!='READY_FOR_APPROVAL_GATES':
        refuse('PH01_INSTALLED_APK_AND_QS_PREFLIGHT_NOT_READY')
    return proof,physical


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('hosted','preflight','navigation','saf-cancel','qs-duplicate-cancel','all'))
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--root',type=Path,default=Path.home()/'Code/bindhosts')
    parser.add_argument('--serial',default=SERIAL)
    parser.add_argument('--output-dir',type=Path,default=Path.home()/'.local/state/bh-app01/p07-ph03')
    parser.add_argument('--ack',default='')
    a=parser.parse_args(argv)
    try:
        if a.serial != SERIAL:refuse('ONLY_LOCALHOST_5555_ACCEPTED')
        if a.mode in ('navigation','saf-cancel','qs-duplicate-cancel','all') and a.ack!=ACK:
            refuse('EXPLICIT_UI_INTERACTION_APPROVAL_REQUIRED')
        if a.mode=='preflight' and a.ack!=READ_ACK:
            refuse('EXPLICIT_READ_ONLY_APPROVAL_REQUIRED')
        out=ph02.private_directory(a.output_dir)
        proof=ph02.verified_hosted(a.root,a.source_sha,out)
        if a.mode=='hosted':
            print('BH_APP01_P07_PH03_HOSTED_GITHUB_AND_APK_PROVENANCE_PASS')
            print('hosted_debug_apk='+str(out/'hosted-app-debug.apk'))
            return 0
        require_target()
        physical=physical_inspect(SERIAL,a.source_sha,out/'hosted-receipt.json')
        if a.mode!='preflight' and (not physical['hosted_apk_matches_installed'] or
                                   physical['read_only_status']!='READY_FOR_APPROVAL_GATES'):
            refuse('PH01_INSTALLED_APK_AND_QS_PREFLIGHT_NOT_READY')
        result={'schema':'bh-app01/p07/ph03-nonroot/v1','source_sha':a.source_sha,
                'serial_hash':physical['serial_hash'],'mode':a.mode,
                'hosted_artifact_id':proof['hosted_artifact_id'],
                'hosted_apk_sha256':proof['hosted_apk_sha256'],
                'installed_apk_sha256':physical['installed_apk_sha256'],
                'installed_apk_matches_hosted':physical['hosted_apk_matches_installed'],
                'root_requests_issued_by_suite':False,'hosts_or_ifw_mutations_issued_by_suite':False,
                'app_install_or_uninstall_performed':False,
                'physical_android16_qualified':False,'release_qualified':False}
        if a.mode=='preflight':result['preflight']=physical
        else:
            if a.mode in ('navigation','all'):result['navigation']=navigation_journey()
            if a.mode in ('saf-cancel','all'):result['saf']=saf_cancel_journey()
            if a.mode in ('qs-duplicate-cancel','all'):result['qs']=qs_duplicate_cancel_journey()
        write_private(out/('ph03-'+a.mode+'.json'),result)
        print('BH_APP01_P07_PH03_'+a.mode.upper().replace('-','_')+'_PASS_NOT_FULL_PHYSICAL_ACCEPTANCE')
        print('report='+str(out/('ph03-'+a.mode+'.json')))
        return 0
    except (Refused,ph02.Refused,ValueError,OSError,subprocess.TimeoutExpired,ET.ParseError) as exc:
        print('BH_APP01_P07_PH03_REFUSED '+str(exc),file=sys.stderr)
        return 12

if __name__=='__main__':sys.exit(run())
