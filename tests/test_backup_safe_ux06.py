#!/usr/bin/env python3
"""UX06 root-only backup acceptance with isolated state; no device mutation."""
from pathlib import Path
import io, os, re, shutil, subprocess, tarfile, tempfile, unittest
MODULE=Path(__file__).resolve().parents[1]/'module'
SCRIPT=MODULE/'config_backup_safe.sh'
FILES=('sources.txt','sources_whitelist.txt','blacklist.txt','whitelist.txt','custom.txt')
class Backups(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='bh-ux06-',dir=os.environ.get('TMPDIR') or None)
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'state';self.root.mkdir()
        self.downloads=Path(self.tmp.name)/'Downloads';self.downloads.mkdir()
        self.scratch=Path(self.tmp.name)/'scratch';self.scratch.mkdir()
        self.env=dict(os.environ, BH_BACKUP_ROOT=str(self.root),BH_BACKUP_MODDIR=str(MODULE),
            BH_BACKUP_DOWNLOAD=str(self.downloads),BH_BACKUP_TEST_MODE='1',
            BH_CONFIG_ROOT=str(self.root), BH_CONFIG_TEST_MODE='1', TMPDIR=str(self.scratch))
        self.data={
            'sources.txt':'https://example.test/source.txt\n',
            'sources_whitelist.txt':'',
            'blacklist.txt':'ads.example.test\n',
            'whitelist.txt':'safe.example.test\n',
            'custom.txt':'127.0.0.1 local.example.test\n'}
        for name,contents in self.data.items(): (self.root/name).write_text(contents)
    def go(self,*args,ok=True,env=None):
        p=subprocess.run(['sh',str(SCRIPT),*args],env=env or self.env,
                         text=True,capture_output=True,timeout=15)
        if ok:self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
        return p
    def create(self):
        out=self.go('create').stdout
        ident=out.split('BH_BACKUP_CREATED: ')[1].strip().splitlines()[0]
        self.assertRegex(ident,r'^bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$')
        return ident
    def test_create_verify_list_private_permissions(self):
        id=self.create();self.assertIn(id,self.go('list').stdout)
        self.assertIn('BH_BACKUP_VERIFY_PASS',self.go('verify',id).stdout)
        self.assertEqual((self.root/'.ux06-backups').stat().st_mode & 0o777,0o700)
        self.assertEqual(self.go('status').stdout.splitlines()[0],'restore_journal=clean')
    def test_restore_replaces_all_five_and_does_not_touch_active_hosts(self):
        id=self.create();(self.root/'hosts').write_text('preserve-hosts\n')
        for name in FILES:(self.root/name).write_text('# changed\n')
        self.go('restore',id)
        for name in FILES:self.assertEqual((self.root/name).read_text(),self.data[name])
        self.assertEqual((self.root/'hosts').read_text(),'preserve-hosts\n')
        self.assertFalse((self.root/'.ux06-restore-pending').exists())
    def test_injected_mid_restore_rollback(self):
        id=self.create()
        for name in FILES:(self.root/name).write_text('# changed\n')
        old={name:(self.root/name).read_bytes() for name in FILES}
        p=self.go('restore',id,ok=False,env={**self.env,'BH_BACKUP_TEST_FAIL_AFTER':'2'})
        self.assertNotEqual(p.returncode,0)
        for name in FILES:self.assertEqual((self.root/name).read_bytes(),old[name])
        self.assertFalse((self.root/'.ux06-restore-pending').exists())
    def test_corrupt_hash_refused_before_writes(self):
        id=self.create();snapshot=self.root/'.ux06-backups'/id
        (snapshot/'blacklist.txt').write_text('other.example.test\n')
        self.assertNotEqual(self.go('verify',id,ok=False).returncode,0)
        before={x:(self.root/x).read_bytes() for x in FILES}
        self.assertNotEqual(self.go('restore',id,ok=False).returncode,0)
        self.assertEqual(before,{x:(self.root/x).read_bytes() for x in FILES})
    def test_invalid_source_restore_refused_even_with_valid_checksum(self):
        id=self.create();snap=self.root/'.ux06-backups'/id
        (snap/'sources.txt').write_text('file:///etc/shadow\n')
        subprocess.run(['sh','-c','sha256sum '+ ' '.join(FILES)+' > SHA256SUMS'],cwd=snap,check=True)
        self.assertNotEqual(self.go('verify',id,ok=False).returncode,0)
    def test_export_import_roundtrip_with_trusted_archive(self):
        id=self.create()
        out=self.go('export',id).stdout
        archive=self.downloads/f'bindhosts-backup-{id}.tar'
        self.assertTrue(archive.is_file(),out)
        self.assertLess(archive.stat().st_size,12000000)
        self.assertIn('BH_BACKUP_IMPORTED:',self.go('import',archive.name).stdout)
        ids=self.go('list').stdout.splitlines()
        self.assertEqual(len(ids),2)
    def test_import_rejects_traversal_and_link_before_extraction(self):
        id=self.create()
        filename=f'bindhosts-backup-{id}.tar'
        tar=self.downloads/filename
        with tarfile.open(tar,'w') as ar:
            data=b'unsafe'
            ti=tarfile.TarInfo('../unsafe');ti.size=len(data)
            ar.addfile(ti,io.BytesIO(data))
        self.assertNotEqual(self.go('import',filename,ok=False).returncode,0)
        self.assertFalse((self.root/'unsafe').exists())
        with tarfile.open(tar,'w') as ar:
            for name in FILES+('SHA256SUMS',):
                entry=tarfile.TarInfo(name);entry.type=tarfile.SYMTYPE;entry.linkname='/etc/hosts'
                ar.addfile(entry)
        self.assertNotEqual(self.go('import',filename,ok=False).returncode,0)
    def test_source_health_only_counts_no_domain_leaks(self):
        (self.root/'sources.txt').write_text('https://first.test/list\nhttps://first.test/list\ndisabled|https://second.test/list\n')
        text=self.go('health').stdout
        self.assertIn('enabled=1|disabled=1|duplicates=1',text)
        self.assertNotIn('first.test',text)
        self.assertNotIn('second.test',text)
    def test_recover_interrupted_restore_journal(self):
        self.create()
        pending=self.root/'.ux06-restore-pending';pending.mkdir()
        for name in FILES: shutil.copyfile(self.root/name,pending/name)
        subprocess.run('sha256sum '+ ' '.join(FILES)+' > SHA256SUMS',cwd=pending,check=True,shell=True)
        (self.root/'blacklist.txt').write_text('danger.example.test\n')
        self.assertIn('BH_BACKUP_RECOVERY_PASS',self.go('recover').stdout)
        self.assertEqual((self.root/'blacklist.txt').read_text(),self.data['blacklist.txt'])
    def test_unknown_backup_id_rejected(self):
        self.assertNotEqual(self.go('restore','../invalid',ok=False).returncode,0)
        self.assertNotEqual(self.go('export','/tmp/foo',ok=False).returncode,0)
if __name__=='__main__':unittest.main(verbosity=2)
