#!/usr/bin/env python3
"""UX09F — source-pinned Android 16 end-to-end acceptance orchestrator.

Prepares exactly qualified artifacts; makes zero device changes without separate opt-in.
No Gradle locally, no automatic reboot/merge, no certificate trust changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.dont_write_bytecode = True
REPO = 'Mikeyphw/bindhosts'
PARENT = 'bd556b508e5e6563858ca08890cdaea245f1f622'
MODULE_RUN = 43546943742
LAB_RUN = 42670772403
LAB_HEAD = 'c76658efeece6a5abb791d721e18b6ee34a7784b'
ARTIFACTS = {'module':'bindhosts-trackerguard-r1', 'v1':'trackerguard-ifw-lab-v1', 'v2':'trackerguard-ifw-lab-v2'}
MODULE = '/data/adb/modules/bindhosts'
STATE = '/data/adb/bindhosts'
MODULE_BLOBS = {
 'hosts_operation_ux09.sh': '66181ac34464d41c44fca195d97c815b419c8b51',
 'source_catalog_batch_ux09.sh': '09ca806c8771e04fb37897804a0a17a2bbb853c6',
 'trackerguard_r2_pm_query.sh': '7a0e339b7cd35faccb6cfdef922a75d489062155',
 'hosts_control_safe.sh': 'c104dcd7ac1fa58d9eadfbaf2cdc67e025ff8401',
 'hosts_update_safe.sh': 'a2a1e2ffc23d0ec2585233656e93f1f17484dc7f',
 'hosts_target_safe.sh': '9a754e34dc159164a467003541c138d11996e051',
 'bindhosts.sh': '45aba09a4cc552b7adb48d124385cb75c09deffb',
 'trackerguard.sh': 'a5ff88bc5801a9117d47be70f769995f000ca825',
 'trackerguard_r2.sh': '702777e8d64def4e4b5125637c55937e58ad176e',
 'response_mode.sh': '05df22759a387998ef2b3aaf20d8b8b0103a3f57',
 'config_backup_safe.sh': '1514380b4305f4caf8b8f2f957264d8a768f70d6',
 'data/r3-lab-signatures.tsv': '8284961fa93ec7cdd4fe944afc0efca5f80afb28',
}
RUNNERS = {
 'ui': ('tests/ux09e_device_acceptance.py','d4d3be5ce37f4c1f6c7b53fbf7b42064e68dc0c8'),
 'r3': ('tests/trackerguard-r3/run_device_acceptance.py','bb165a42ed62d28721104e905100328e4fced01e'),
 'mount': ('tests/hosts-mount-acceptance.sh','428939e3b554351deb64c20063bbaee952a89899'),
}
SERIAL = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')
HEX = re.compile(r'^[a-f0-9]{64}$')
LAB_PKG = 'com.mikeyphw.trackerguard.ifwlab'

class Refused(RuntimeError): pass

def need(value, message):
    if not value: raise Refused(message)

def print_status(marker, value=''):
    print(f'BH_UX09F_{marker}' + (' '+str(value) if value!='' else ''), flush=True)

def run(argv, *, cwd=None, timeout=180, check=True, binary=False, stdin=None, capture=True):
    try:
        p=subprocess.run(list(map(str,argv)),cwd=cwd,input=stdin,capture_output=capture,
                         text=(not binary),timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Refused('command unavailable/timed out: '+str(argv[0])+' '+type(exc).__name__) from exc
    if check and p.returncode:
        # Do not expose unredacted backend output (paths, domains or app lists).
        raise Refused(f'command failed rc={p.returncode}: {Path(str(argv[0])).name}')
    return p

def git(repo, *args, binary=False):
    p=run(['git',*args],cwd=repo,binary=binary)
    return p.stdout if binary else p.stdout.strip()

def safe_path(path:Path):
    need(path.is_dir() and not path.is_symlink(),'workspace unavailable/unsafe')
    need((path.stat().st_mode&0o077)==0,'workspace must be private (chmod 700)')
    return path

def workspace(custom=None):
    p=Path(custom).expanduser() if custom else Path.home()/'.local/share/bindhosts-ux09f'/PARENT[:12]
    if p.exists(): return safe_path(p.resolve())
    p.mkdir(mode=0o700,parents=True,exist_ok=False)
    p.chmod(0o700)
    return safe_path(p.resolve())

def write_private(path, data):
    need(not path.is_symlink(),'refusing symlink output')
    tmp=path.with_suffix(path.suffix+'.tmp')
    need(not tmp.is_symlink(),'refusing symlink temporary file')
    with tmp.open('wb') as f:f.write(data)
    tmp.chmod(0o600)
    tmp.replace(path)
    path.chmod(0o600)

def save_json(path, obj):
    write_private(path,(json.dumps(obj,sort_keys=True,indent=2)+'\n').encode())

def read_json(path):
    need(path.is_file() and not path.is_symlink(),'missing private receipt: '+path.name)
    try:return json.loads(path.read_text())
    except (OSError,ValueError,UnicodeDecodeError) as exc:
        raise Refused('private JSON receipt unreadable/corrupt: '+path.name) from exc

def blob(repo, path, expected):
    need(re.fullmatch(r'[A-Za-z0-9_./-]+',path) is not None and '..' not in Path(path).parts,'unsafe source path')
    got=git(repo,'rev-parse',f'{PARENT}:{path}')
    need(got==expected,'Git blob drift: '+path)
    p=run(['git','show',f'{PARENT}:{path}'],cwd=repo,binary=True)
    need(len(p.stdout)>100,'empty pinned source: '+path)
    return p.stdout

def repo_check(repo):
    need((repo/'.git').exists(),'local bindhosts repository missing')
    url=git(repo,'remote','get-url','origin')
    need(re.fullmatch(r'(?:git@github\.com:|https://github\.com/)Mikeyphw/bindhosts(?:\.git)?/?',url) is not None,'unexpected GitHub origin')
    need(git(repo,'cat-file','-t',PARENT)=='commit','UX09E parent commit not available locally')
    return repo

def sha(data):return hashlib.sha256(data).hexdigest()

def gh_json(repo, *args):
    p=run(['gh',*args],cwd=repo)
    try:return json.loads(p.stdout)
    except ValueError:raise Refused('invalid GitHub JSON')

def check_hosted_run(repo, runid, head, artifact_names):
    info=gh_json(repo,'api',f'repos/{REPO}/actions/runs/{runid}')
    need(info.get('head_sha')==head and info.get('conclusion')=='success' and info.get('status')=='completed',
         f'run {runid} does not match qualified commit')
    arts=gh_json(repo,'api',f'repos/{REPO}/actions/runs/{runid}/artifacts')
    selected={}
    for name in artifact_names:
        matches=[x for x in arts.get('artifacts',[]) if x.get('name')==name and not x.get('expired')]
        need(len(matches)==1,'artifact missing/ambiguous/expired: '+name)
        selected[name]={'id':matches[0]['id'],'size':matches[0]['size_in_bytes']}
    return selected

def safe_extract_archive(raw_zip:Path,dest:Path, ext):
    need(raw_zip.is_file() and not raw_zip.is_symlink(),'download missing: '+str(raw_zip))
    with zipfile.ZipFile(raw_zip) as z:
        need(z.testzip() is None,'corrupt hosted archive')
        files=[x for x in z.infolist() if not x.is_dir()]
        need(len(files)==1,'expected one delivered '+ext+'; got '+str(len(files)))
        f=files[0];n=Path(f.filename)
        need(not n.is_absolute() and '..' not in n.parts and n.suffix==ext and
             f.file_size <= 40*1024*1024 and (f.external_attr>>16)&0o170000 != 0o120000,
             'unsafe hosted archive member')
        data=z.read(f)
    need(len(data)>=1024,'empty hosted binary')
    write_private(dest,data)
    return data

def downloaded_one(repo, runid, artname, suffix, destination):
    # gh run download extracts its artifact ZIP into an empty TMPDIR staging area.
    temp_root=os.environ.get('TMPDIR')
    need(temp_root and Path(temp_root).is_dir(),'set TMPDIR for temporary extraction')
    with tempfile.TemporaryDirectory(dir=temp_root,prefix='bh-ux09f-gh-') as d:
        run(['gh','run','download',str(runid),'-R',REPO,'-n',artname,'-D',d],cwd=repo,timeout=180)
        files=[x for x in Path(d).rglob('*') if x.is_file()]
        need(len(files)==1,'artifact contents not a single file: '+artname)
        candidate=files[0]
        need(candidate.suffix==suffix and not candidate.is_symlink() and candidate.stat().st_size < 45*1024*1024,
             'invalid artifact file: '+artname)
        data=candidate.read_bytes()
        need(len(data)>=1024,'artifact too small')
        write_private(destination,data)
        return data

def inspect_module(contents,repo):
    with zipfile.ZipFile(contents) as z:
        need(z.testzip() is None,'invalid module ZIP CRC')
        names=z.namelist();need(len(set(names))==len(names),'duplicate module entry names')
        for n in names:
            p=Path(n)
            need(not p.is_absolute() and '..' not in p.parts,'module ZIP traversal refused')
        need('module.prop' in names,'module.prop missing')
        meta=z.read('module.prop').decode('utf-8',errors='replace')
        need('id=bindhosts\n' in meta,'unrecognized KernelSU module')
        need('versionCode=21611\n' in meta,'unexpected module version')
        for name,blobid in MODULE_BLOBS.items():
            need(name in names,'module script absent: '+name)
            expected=blob(repo,'module/'+name,blobid)
            need(z.read(name)==expected,'module script does not match qualified source: '+name)
        for name in ['webroot/index.html','META-INF/com/google/android/update-binary',
                     'bin/arm64-v8a/axmlscan','bin/arm64-v8a/blocked_response',
                     'bin/arm64-v8a/blocked_response_tls','data/r3-lab-signatures.tsv']:
            need(name in names and z.getinfo(name).file_size>0,'module payload incomplete: '+name)
        # A copied-but-incorrect binary architecture is not a successful ABI build.
        for elf in ('axmlscan','blocked_response','blocked_response_tls'):
            b=z.read('bin/arm64-v8a/'+elf)
            need(len(b)>1024 and b[:5]==b'\x7fELF\x02' and b[5]==1 and
                 int.from_bytes(b[18:20],'little')==183,
                 'native library not a valid ARM64 ELF: '+elf)
    return {n:sha(blob(repo,'module/'+n,b)) for n,b in MODULE_BLOBS.items()}

def check_lab(apk,version):
    need(apk.is_file() and apk.stat().st_size>=1024,'lab APK missing')
    info=run(['aapt','dump','badging',str(apk)],timeout=30).stdout
    perms=run(['aapt','dump','permissions',str(apk)],timeout=30).stdout
    match=re.search(r"^package: name='([^']+)' versionCode='([^']+)'",info,re.M)
    need(match is not None and match.groups()==(LAB_PKG,str(version)),'lab APK package/version mismatch')
    need('uses-permission:' not in info and 'uses-permission:' not in perms,'unexpected lab permission')

def prepare(repo,ws):
    repo_check(repo)
    m=check_hosted_run(repo,MODULE_RUN,PARENT,[ARTIFACTS['module']])
    l=check_hosted_run(repo,LAB_RUN,LAB_HEAD,[ARTIFACTS['v1'],ARTIFACTS['v2']])
    result={}
    for key,name,runid,filename,ext in [
      ('module',ARTIFACTS['module'],MODULE_RUN,'bindhosts-ux09e-qualified.zip','.zip'),
      ('v1',ARTIFACTS['v1'],LAB_RUN,'trackerguard-ifw-lab-v1.apk','.apk'),
      ('v2',ARTIFACTS['v2'],LAB_RUN,'trackerguard-ifw-lab-v2.apk','.apk')]:
        path=ws/filename
        # Preserve an existing prepared artifact if hash receipt confirms its identity.
        prior=None
        if (ws/'artifacts.json').is_file():
            prior=read_json(ws/'artifacts.json').get('files',{}).get(key)
        if path.is_file() and prior and prior.get('sha256')==sha(path.read_bytes()):
            data=path.read_bytes()
            print_status('PREPARE_REUSE',key)
        else:
            data=downloaded_one(repo,runid,name,ext,path)
        result[key]={'file':filename,'sha256':sha(data),'run':runid,
                     'artifact_id':(m if key=='module' else l)[name]['id'],'bytes':len(data)}
        print_status('PREPARE_ARTIFACT',f'{key} sha256={result[key]["sha256"]}')
    wanted=inspect_module(ws/result['module']['file'],repo)
    check_lab(ws/result['v1']['file'],1)
    check_lab(ws/result['v2']['file'],2)
    need(result['v1']['sha256']!=result['v2']['sha256'],'lab versions identical')
    manifest={'schema':'BH_UX09F_PREPARE_V1','source_sha':PARENT,'module_run':MODULE_RUN,
              'lab_run':LAB_RUN,'files':result,'module_script_sha256':wanted,'created_at':int(time.time())}
    save_json(ws/'artifacts.json',manifest)
    for kind,(path,b) in RUNNERS.items():blob(repo,path,b)
    print_status('PREPARE_PASS',f'exact-run module, v1/v2 lab APKs and 3 pinned runners ready in {ws}')
    return manifest

def prepared(repo,ws):
    d=read_json(ws/'artifacts.json')
    need(d.get('schema')=='BH_UX09F_PREPARE_V1' and d.get('source_sha')==PARENT and
         d.get('module_run')==MODULE_RUN and d.get('lab_run')==LAB_RUN,'invalid prepared artifact manifest')
    for k,v in d['files'].items():
        p=ws/v['file'];need(p.is_file() and not p.is_symlink() and sha(p.read_bytes())==v['sha256'],'artifact integrity changed: '+k)
    inspect_module(ws/d['files']['module']['file'],repo)
    check_lab(ws/d['files']['v1']['file'],1)
    check_lab(ws/d['files']['v2']['file'],2)
    return d

class Device:
    def __init__(self,serial):
        need(bool(SERIAL.fullmatch(serial)),'unsafe ADB serial')
        self.serial=serial
    def adb(self,*args,check=True,binary=False,stdin=None,timeout=90):
        return run(['adb','-s',self.serial,*args],check=check,binary=binary,stdin=stdin,timeout=timeout)
    def root(self,command,check=True,timeout=90):
        return self.adb('shell','su','-c',command,check=check,timeout=timeout).stdout.replace('\r','')
    def simple(self,*args):return self.adb('shell',*args).stdout.strip().replace('\r','')
    def fingerprint(self,path):
        need(path in (f'{MODULE}/{n}' for n in MODULE_BLOBS),'unapproved hash path')
        result=self.root(f'if [ -f {path} ] && [ ! -L {path} ]; then sha256sum {path}; else echo ABSENT; fi').strip()
        if result=='ABSENT':return None
        match=re.fullmatch(r'([0-9a-f]{64})\s+\S+',result)
        need(match is not None,'invalid device script hash')
        return match.group(1)
    def probe(self,repo):
        need(self.adb('get-state').stdout.strip()=='device','ADB target not connected')
        api=self.simple('getprop','ro.build.version.sdk');abi=self.simple('getprop','ro.product.cpu.abi')
        uid=self.root('id -u').strip()
        need(uid=='0','KernelSU root not available')
        se=self.simple('getenforce')
        need(se in ('Enforcing','Permissive'),'SELinux mode unrecognized')
        pins={}
        for n,b in MODULE_BLOBS.items():
            expected=sha(blob(repo,'module/'+n,b))
            actual=self.fingerprint(MODULE+'/'+n)
            pins[n]={'match':actual==expected,'present':actual is not None}
        # A real usable root PM inventory, never classify help output as package rows.
        pm=self.root('/system/bin/pm list packages').splitlines()
        count=sum(x.startswith('package:') for x in pm)
        need(count>0 and count==len(pm),'root PackageManager inventory invalid')
        status=self.root(f'sh {MODULE}/bindhosts.sh --hosts-control status',check=all(v['present'] for v in pins.values())) if all(v['present'] for v in pins.values()) else ''
        state=re.search(r'^BH_HOSTS_STATE=(ACTIVE|PAUSED|INACTIVE|DISABLED)$',status,re.M)
        record={'api':api,'abi':abi,'root_uid':uid,'selinux':se,'pm_packages':count,'script_pins':pins,
                'hosts_state':state.group(1) if state else 'UNKNOWN',
                'module_verified':all(v['match'] for v in pins.values()),'serial':self.serial,'run_source':PARENT,
                'timestamp':int(time.time())}
        print_status('DEVICE_PROBE',json.dumps(record,sort_keys=True))
        if api!='36' or abi!='arm64-v8a':print_status('DEVICE_VARIANT_NOT_QUALIFIED',f'API={api} ABI={abi}')
        if not record['module_verified']:print_status('INSTALL_OR_REBOOT_REQUIRED','module files do not match exact qualified UX09E artifact')
        return record
    def root_script_stdin(self,script,args=(),timeout=100):
        # Stream a source-pinned test script through an already proven root child
        # shell transport. Read-only mode makes no writes to device files.
        payload=b'set -- '+b' '.join(x.encode() for x in args)+b'\n'+script
        p=self.adb('shell','-T','su','-c','/system/bin/sh',binary=True,stdin=payload,check=False,timeout=timeout)
        text=p.stdout.decode('utf-8','replace').replace('\r','')
        if p.returncode:raise Refused(f'root streamed mount test refused rc={p.returncode}; refer to local evidence')
        return text
    def screenshot(self,destination):
        data=self.adb('exec-out','screencap','-p',binary=True).stdout
        need(data.startswith(b'\x89PNG\r\n\x1a\n'),'screenshot PNG invalid')
        write_private(destination,data)
    def rule_fingerprints(self):
        # Only preapproved rule/config paths; no rule bytes are returned to Termux.
        result={}
        for name in ('sources.txt','sources_whitelist.txt','blacklist.txt','whitelist.txt','custom.txt'):
            path=STATE+'/'+name
            output=self.root(f'if [ -f {path} ] && [ ! -L {path} ]; then sha256sum {path}; else echo ABSENT; fi').strip()
            if output=='ABSENT':result[name]='ABSENT';continue
            m=re.fullmatch(r'([a-f0-9]{64})\s+\S+',output)
            need(m is not None,'invalid rule file fingerprint: '+name)
            result[name]=m.group(1)
        return result
    def response_mode(self):
        output=self.root(f'sh {MODULE}/bindhosts.sh --response status')
        m=re.search(r'^mode=(off|transparent|logo)$',output,re.M)
        need(m is not None,'HTTP response mode unavailable')
        return m.group(1)

def require_target(state):
    need(state.get('module_verified') and state.get('api')=='36' and
         state.get('abi')=='arm64-v8a' and state.get('selinux')=='Enforcing',
         'physical acceptance writes require exact UX09E module, Android API36 arm64-v8a, SELinux enforcing')

def receipt(ws,name, data):
    record={'schema':'BH_UX09F_RECEIPT_V1','stage':name,'source_sha':PARENT,
            'timestamp':int(time.time()),**data}
    save_json(ws/(name+'.json'),record)
    print_status('RECEIPT',str(ws/(name+'.json')))

def install(repo,ws,dev):
    m=prepared(repo,ws)
    state=dev.probe(repo)
    if state['module_verified']:
        print_status('INSTALL_UNNECESSARY','qualified module already installed')
        return
    print_status('INSTALL_WARNING','KernelSU module installation writes to the device; reboot is manual.')
    need(input('Type I_AUTHORIZE_KERNELSU_FINAL_INSTALL: ').strip()=='I_AUTHORIZE_KERNELSU_FINAL_INSTALL',
         'install authorization missing')
    p=ws/m['files']['module']['file']
    out=run(['su','-c','ksud module install '+shlex.quote(str(p))],timeout=240,check=False)
    need(out.returncode==0,'KernelSU refused module installation')
    receipt(ws,'install',{'result':'INSTALL_REQUEST_SUCCEEDED','module_sha256':sha(p.read_bytes()),'reboot_required':True,'serial':dev.serial})
    print_status('INSTALL_PASS_REBOOT_REQUIRED','reboot manually, then run probe; do not qualify until post-reboot pins match')

def pin_runner(repo,name,ws):
    path,wanted=RUNNERS[name]
    data=blob(repo,path,wanted)
    p=ws/('pinned-'+name+('-runner.py' if name!='mount' else '-runner.sh'))
    write_private(p,data)
    return p

def ui(repo,ws,dev,*,capture=False,all_tests=True):
    state=dev.probe(repo)
    require_target(state)
    runner=pin_runner(repo,'ui',ws)
    cmd=[sys.executable,'-B',str(runner),'walk','--serial',dev.serial,
         '--output-dir',str(ws),'--ack','I_AUTHORIZE_UX09_MANUAL_UI_ACCEPTANCE']
    if all_tests: cmd+=['--test-toggle','--test-source','--test-update']
    if capture:cmd+=['--capture']
    p=run(cmd,check=False,timeout=7200,capture=False)
    receipt(ws,'ui',{'result':'PASS' if p.returncode==0 else 'REFUSED','manual_only':True,
                     'performed':'full' if all_tests else 'visual', 'exit_code':p.returncode,'serial':dev.serial})
    need(p.returncode==0,'UX09E physical UI walkthrough failed or was refused')
    print_status('UI_MANUAL_AND_READBACK_PASS','see original UX09E JSON evidence for exact checks')

def mount(repo,ws,dev,live=False):
    state=dev.probe(repo)
    if live:require_target(state)
    else:need(state['module_verified'],'mount acceptance requires installed qualified module')
    script=blob(repo,*RUNNERS['mount'])
    if live:
        print_status('MOUNT_LIVE_WARNING','writes a temporary marker to actual hosts, then restores exact baseline')
        need(input('Type I_AUTHORIZE_HOSTS_MOUNT_ROUNDTRIP: ').strip()=='I_AUTHORIZE_HOSTS_MOUNT_ROUNDTRIP',
             'mount live authorization missing')
    output=dev.root_script_stdin(script,['--probe-live','--accept-risk'] if live else ['--read-only'],timeout=180)
    marker='BH_ACCEPT_LIVE_ROUNDTRIP_PASS' if live else 'BH_ACCEPT_READ_ONLY_PASS'
    need(marker in output,'mount acceptance marker absent')
    receipt(ws,'mount-live' if live else 'mount-probe',{'result':'PASS','marker':marker,'mount_mode':'live' if live else 'read-only','serial':dev.serial})
    print_status(marker)

def r3(repo,ws,dev,live=False):
    state=dev.probe(repo)
    if live:require_target(state)
    else:need(state['module_verified'],'R3 needs installed HF04 + UX09E module')
    runner=pin_runner(repo,'r3',ws)
    if live:
        manifest=prepared(repo,ws)
        apks=[ws/manifest['files'][k]['file'] for k in ('v1','v2')]
        print_status('R3_LIVE_WARNING','installs/updates/uninstalls isolated lab app and modifies/restores its IFW rules')
        need(input('Type I_AUTHORIZE_R3_LAB_LIFECYCLE: ').strip()=='I_AUTHORIZE_R3_LAB_LIFECYCLE',
             'R3 live authorization missing')
        argv=[sys.executable,'-B',str(runner),'--serial',dev.serial,'--run','--accept-device-writes',
              '--apk-v1',str(apks[0]),'--apk-v2',str(apks[1])]
    else:argv=[sys.executable,'-B',str(runner),'--serial',dev.serial,'--read-only']
    p=run(argv,check=False,timeout=7200,capture=True)
    # Original harness may expose package names/error details: keep raw logs private.
    log=ws/('r3-live.log' if live else 'r3-probe.log')
    write_private(log,((p.stdout or '')+'\n'+(p.stderr or '')).encode())
    good=p.returncode==0 and ('TG_R3_LIVE_ACCEPTANCE_PASS' if live else 'TG_R3_READ_ONLY_INSPECTION_PASS') in (p.stdout or '')
    receipt(ws,'r3-live' if live else 'r3-probe',{'result':'PASS' if good else 'REFUSED',
       'exit_code':p.returncode,'marker':'TG_R3_LIVE_ACCEPTANCE_PASS' if good and live else
       'TG_R3_READ_ONLY_INSPECTION_PASS' if good else 'NOT_VERIFIED','log_file':log.name,'serial':dev.serial})
    need(good,'R3 acceptance not qualified; inspect private log '+str(log))
    print_status('R3_LIVE_PASS' if live else 'R3_PROBE_PASS',str(log))

MANUAL_CHECKS=[
 ('home-status','Home dashboard status and blocked-domain search results render with no broken scrolling'),
 ('sources-presets','Sources Presets/My sources/Advanced and Energized mutually-exclusive selections are usable'),
 ('rules-editor','Rules: custom hosts, allowlist, blacklist, source fields and safe edit buttons render correctly'),
 ('apps-rules','Apps: TrackerGuard per-app scan, manual vs automatic IFW rule ownership and scoped controls are intelligible'),
 ('activity-diagnostics','Activity: operation history, diagnostic counts and redacted export controls render'),
 ('backup-safe','More: private backup and source-health controls render correctly; actual backup/restore is verified separately'),
 ('blocked-page-http','More: HTTP off/transparent/logo controls display correctly; actual mode restoration is verified separately'),
 ('blocked-page-https','More: HTTPS CA opt-in trust warnings, certificate fingerprint and disable controls are present; do not install a CA'),
 ('mobile-layout','Android 16: no status-bar overlap, horizontal overflow, broken scroll, clipped buttons or navigation'),
 ('operation-close','UX09 operation terminal closes without canceling a running operation; View update log reopens it'),
 ('failure-feedback','Missing data/refusal states show explicit error/read-back text rather than false green success'),
 ('quick-settings','Quick settings tile, cron settings, and module status are visible without unexpected automatic writes'),
]

def approval(token, warning):
    print_status('LIVE_WRITE_WARNING',warning)
    need(input('Type '+token+' to authorize: ').strip()==token,'explicit acceptance authorization missing: '+token)

def confirmation(instruction):
    print('\n'+instruction,flush=True)
    need(input('Confirm the described step was completed [y/N]: ').strip().lower()=='y',
         'manual step not confirmed; do not infer success')

def rules_live(repo,ws,dev):
    require_target(dev.probe(repo))
    approval('I_AUTHORIZE_TEST_RULE_EDIT_AND_RESTORE',
       'manual temporary edits to your real Rules files; no automatic hosts Update; MUST restore exact prior bytes')
    baseline=dev.rule_fingerprints()
    for kind,name,value in [('blacklist','blacklist.txt','ux09f-black.invalid'),
                            ('whitelist','whitelist.txt','ux09f-allow.invalid'),
                            ('custom','custom.txt','127.0.0.1 ux09f-custom.invalid')]:
        confirmation(f'In bindhosts → Rules → {kind}, add this temporary test entry (do NOT click Update hosts): {value}')
        now=dev.rule_fingerprints()
        need(now[name]!=baseline[name],'Rules editor did not change '+name)
        need(all(now[k]==baseline[k] for k in baseline if k!=name),'Rules edited another file unexpectedly; STOP')
        confirmation(f'In Rules → {kind}, remove exactly that temporary entry and save; leave unrelated entries unchanged.')
        need(dev.rule_fingerprints()==baseline,'Rules file bytes not restored after '+kind+' round trip; STOP')
    receipt(ws,'rules-live',{'result':'PASS','test_types':['blacklist','whitelist','custom'],'restored':True,'serial':dev.serial})
    print_status('RULES_EDITOR_ROUNDTRIP_PASS','three per-kind changes restored byte-for-byte')

def backup_live(repo,ws,dev):
    require_target(dev.probe(repo))
    approval('I_AUTHORIZE_PRIVATE_BACKUP_RESTORE_TEST',
        'create one new PRIVATE backup, verify/preview and restore that exact backup via More UI')
    before=dev.rule_fingerprints()
    confirmation('In More → Backups & source health, tap Create backup. Confirm the new private backup appears in the selector.')
    confirmation('Select that NEW backup. Tap Verify & preview and confirm the app reports a successful verification.')
    confirmation('Without changing Rules, restore that exact new backup through the explicit UI confirmation. Do not import/export other archives.')
    need(dev.rule_fingerprints()==before,'backup Restore did not preserve original configuration bytes; STOP')
    receipt(ws,'backup-live',{'result':'PASS','rules_restored':True,'manual_verified':True,'serial':dev.serial})
    print_status('PRIVATE_BACKUP_ROUNDTRIP_PASS','original rule file fingerprints unchanged')

def response_live(repo,ws,dev):
    require_target(dev.probe(repo))
    before=dev.response_mode();host=dev.root(f'sh {MODULE}/bindhosts.sh --hosts-control status')
    approval('I_AUTHORIZE_HTTP_RESPONSE_MODE_ROUNDTRIP',
             'manual HTTP-only mode change and restoration; do NOT enable HTTPS or install a certificate')
    target='transparent' if before!='transparent' else 'off'
    confirmation(f'In More → Blocked-page response, apply HTTP mode {target}. Do NOT generate a CA or enable HTTPS.')
    need(dev.response_mode()==target,'HTTP response mode did not reach requested test setting')
    confirmation(f'Restore the ORIGINAL HTTP response mode: {before}, and verify the page reports the original mode.')
    need(dev.response_mode()==before,'original HTTP response mode NOT restored; STOP')
    need(dev.root(f'sh {MODULE}/bindhosts.sh --hosts-control status')==host,
         'hosts status changed during HTTP mode round trip; STOP')
    receipt(ws,'response-live',{'result':'PASS','restored_mode':before,'https_ca_not_touched':True,'serial':dev.serial})
    print_status('HTTP_MODE_ROUNDTRIP_PASS',before)

def manual(ws,dev,*,capture=False):
    print_status('MANUAL_SCOPE','visual checks only; backup, Rules and HTTP round trips have separate explicit gates')
    record={'mode':'manual-observation','results':{},'screenshots':[]}
    old=(ws/'manual.json')
    if old.is_file():
        previous=read_json(old)
        record['results'].update(previous.get('results',{}))
        record['screenshots'].extend(previous.get('screenshots',[]))
    for idx,(ident,description) in enumerate(MANUAL_CHECKS,1):
        if record['results'].get(ident)=='PASS': continue
        print(f'\n[{idx}/{len(MANUAL_CHECKS)}] {description}\nOpen bindhosts WebUI and verify this exact behavior.',flush=True)
        value=input('Observed result [p]ass / [f]ail / [s]kip / [q]uit: ').strip().lower()
        if value=='q':break
        need(value in ('p','f','s'),'expected p/f/s/q')
        result={'p':'PASS','f':'FAIL','s':'PENDING'}[value]
        record['results'][ident]=result
        if capture and value!='s':
            path=ws/f'ui-manual-{ident}-{int(time.time())}.png'
            dev.screenshot(path);record['screenshots'].append(path.name)
        save_json(old,record)
    complete=all(record['results'].get(i)=='PASS' for i,_ in MANUAL_CHECKS)
    receipt(ws,'manual-matrix',{'result':'PASS' if complete else 'INCOMPLETE',
         'counts':{s:sum(record['results'].get(i)==s for i,_ in MANUAL_CHECKS) for s in ('PASS','FAIL','PENDING')},'serial':dev.serial})
    print_status('MANUAL_MATRIX_PASS' if complete else 'MANUAL_MATRIX_INCOMPLETE')
    need(complete,'manual UI matrix has failed/skipped/unfinished checks; do not continue to later live gates')

def report(ws):
    stages=['mount-probe','mount-live','r3-probe','r3-live','ui','manual-matrix','rules-live','backup-live','response-live']
    data={}
    for stage in stages:
        f=ws/(stage+'.json')
        if not f.exists():
            data[stage]={'result':'PENDING'}
            continue
        x=read_json(f)
        valid=(x.get('schema')=='BH_UX09F_RECEIPT_V1' and x.get('source_sha')==PARENT
               and x.get('stage')==stage and isinstance(x.get('timestamp'),int)
               and x['timestamp']>1700000000 and bool(SERIAL.fullmatch(x.get('serial',''))))
        result=x.get('result','UNKNOWN') if valid else 'INVALID_RECEIPT'
        if stage=='manual-matrix' and result=='PASS':
            manual=read_json(ws/'manual.json') if (ws/'manual.json').is_file() else {}
            if not all(manual.get('results',{}).get(i)=='PASS' for i,_ in MANUAL_CHECKS):
                result='INCOMPLETE_MANUAL_EVIDENCE'
        if stage=='ui' and result=='PASS':
            logs=sorted(ws.glob('ux09e-*.json'))
            valid_ui=False
            for entry in logs:
                try:
                    witness=read_json(entry)
                    required={'sources-topology','rules-buttons','response-settings','blocking-toggle-first',
                              'blocking-toggle-restore','toggle-readback-restored','source-selection-saved',
                              'source-selection-restored','source-byte-restore-pass','update-terminal','update-backend-receipt'}
                    if witness.get('source_sha')=='f32076e87164499ad693f9365c30a622e0fcc832' and \
                       witness.get('outcome')=='MANUAL_UI_AND_BACKEND_UPDATE_PASS_TOGGLE_VERIFIED_SOURCE_RESTORED' and \
                       required<=set(witness.get('manual_checks',[])):
                        valid_ui=True
                        break
                except (OSError,ValueError,TypeError):pass
            if not valid_ui:result='MISSING_UX09E_READBACK_EVIDENCE'
        data[stage]={'result':result,'timestamp':x.get('timestamp')}
    serials={read_json(ws/(stage+'.json')).get('serial') for stage in stages
             if (ws/(stage+'.json')).exists() and data[stage]['result']=='PASS'}
    full=all(x['result']=='PASS' for x in data.values()) and len(serials)==1
    if len(serials)>1:print_status('MIXED_DEVICE_RECEIPTS_REFUSED','physical stages used different ADB serials')
    save_json(ws/'final-summary.json',{'source_sha':PARENT,'stages':data,'device_serial':next(iter(serials)) if len(serials)==1 else None,
                                       'complete':full,'timestamp':int(time.time())})
    print_status('FINAL_ACCEPTANCE_PASS' if full else 'FINAL_ACCEPTANCE_PENDING',json.dumps(data,sort_keys=True))
    print_status('FINAL_REPORT',str(ws/'final-summary.json'))
    return full

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','install','probe','ui','manual','mount','r3','rules','backup','response','report','full'))
    p.add_argument('--repo',default=str(Path.home()/'Code/bindhosts'))
    p.add_argument('--serial',default='localhost:5555')
    p.add_argument('--workspace',default=None)
    p.add_argument('--capture',action='store_true',help='explicit local screenshots; can include private screen content')
    p.add_argument('--live',action='store_true',help='requires separate typed authorization for device writes')
    p.add_argument('--visual-only',action='store_true',help='UI checks without Pause/Resume, source save or hosts update')
    args=p.parse_args(argv)
    repo=repo_check(Path(args.repo).expanduser().resolve())
    ws=workspace(args.workspace)
    if args.command=='prepare':prepare(repo,ws);return 0
    if args.command=='report':return 0 if report(ws) else 3
    d=Device(args.serial)
    if args.command=='probe':
        data=d.probe(repo);receipt(ws,'device-probe',{'result':'PASS' if data['module_verified'] else 'INSTALL_REQUIRED',**data})
        if data['module_verified']:
            mount(repo,ws,d,live=False);r3(repo,ws,d,live=False)
        return 0 if data['module_verified'] else 3
    if args.command=='install':install(repo,ws,d)
    elif args.command=='ui':ui(repo,ws,d,capture=args.capture,all_tests=not args.visual_only)
    elif args.command=='manual':
        need(d.probe(repo)['module_verified'],'manual check requires UX09E installed')
        manual(ws,d,capture=args.capture)
    elif args.command=='rules':rules_live(repo,ws,d)
    elif args.command=='backup':backup_live(repo,ws,d)
    elif args.command=='response':response_live(repo,ws,d)
    elif args.command=='mount':mount(repo,ws,d,live=args.live)
    elif args.command=='r3':r3(repo,ws,d,live=args.live)
    elif args.command=='full':
        # Deliberately do not install or reboot: operator must do so separately.
        require_target(d.probe(repo))
        mount(repo,ws,d,live=False)
        r3(repo,ws,d,live=False)
        ui(repo,ws,d,capture=args.capture,all_tests=True)
        rules_live(repo,ws,d)
        backup_live(repo,ws,d)
        response_live(repo,ws,d)
        manual(ws,d,capture=args.capture)
        mount(repo,ws,d,live=True)
        r3(repo,ws,d,live=True)
        need(report(ws),'final physical acceptance incomplete; inspect report and resume missing gates')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (Refused,KeyboardInterrupt) as exc:
        print_status('REFUSED',str(exc) if str(exc) else 'interrupted')
        sys.exit(2)
