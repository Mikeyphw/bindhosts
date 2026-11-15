"""PH03 negative/positive safety and UI-tree cases, with no device/GitHub access."""
import contextlib
import io
import pathlib
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / 'scripts/ci'))
import bh_app01_p07_ph03 as p


def hierarchy(*, show='home', modal=False):
    items=['<node text="" bounds="[0,0][900,2000]"/>']
    for name,label in [('home','Home'),('rules','Rules'),('apps','Apps'),('more','More')]:
        idx=['home','rules','apps','more'].index(name)
        items.append(f'<node text="{label}" bounds="[{idx*210+15},1850][{idx*210+195},1980]"/>')
    key={'home':'App tracker protection','rules':'Blocking controls',
         'apps':'TrackerGuard','more':'Activity &amp; diagnostics'}[show]
    items.append('<node text="'+key+'" bounds="[20,220][480,300]"/>')
    if modal:
        items.append('<node text="Update Bindhosts rules?" bounds="[90,500][600,550]"/>')
        items.append('<node text="Cancel" clickable="true" enabled="true" bounds="[100,900][230,980]"/>')
    return ('<hierarchy rotation="0">'+''.join(items)+'</hierarchy>').encode()


class FakeResult:
    def __init__(self,out=b'',rc=0):self.stdout=out;self.stderr=b'';self.returncode=rc


class PH03SourceAndSafety(unittest.TestCase):
    def test_fixed_serial_action_and_mode_gate_before_proof_or_device(self):
        for arg in ('navigation','saf-cancel','qs-duplicate-cancel','all'):
            with self.subTest(arg=arg):
                with patch.object(p.ph02,'verified_hosted',side_effect=AssertionError('GH called')):
                    with contextlib.redirect_stderr(io.StringIO()) as capture:
                        rc=p.run([arg,'--source-sha','a'*40])
                self.assertEqual(rc,12)
                self.assertIn('EXPLICIT_UI_INTERACTION',capture.getvalue())
        with patch.object(p.ph02,'verified_hosted',side_effect=AssertionError('GH called')):
            with contextlib.redirect_stderr(io.StringIO()) as capture:
                rc=p.run(['navigation','--source-sha','a'*40,'--serial','emulator-5554','--ack',p.ACK])
        self.assertEqual(rc,12)
        self.assertIn('LOCALHOST_5555',capture.getvalue())

    def test_reject_dangerous_adb_and_arbitrary_paths(self):
        bad=[['install','/tmp/fake.apk'],['shell','su','-c','id'],
             ['shell','am','force-stop',p.APP],['shell','pm','clear',p.APP],
             ['shell','input','text','Update'],['shell','sh','-c','echo hi'],
             ['shell','rm','-rf','/sdcard'],['shell','input','tap','123;sh','43'],
             ['shell','uiautomator','dump','/sdcard/Download/private.xml'],
             ['shell','input','keyevent','KEYCODE_ENTER']]
        for op in bad:
            with self.subTest(op=op),self.assertRaises(p.Refused):p.validate_command(op,p.temp_path('a'*16))
        for op in [['shell','input','tap','1','2'],
                   ['shell','am','start','-W','-n',p.APP_COMPONENT,'-a',p.QS_ACTION],
                   ['shell','input','keyevent','KEYCODE_BACK'],
                   ['exec-out','cat',p.temp_path('a'*16)]]:
            p.validate_command(op,p.temp_path('a'*16))

    def test_temp_ownership_and_bounds(self):
        for name in ['abc','../../secret','g'*16,'a'*17]:
            with self.subTest(nonce=name),self.assertRaises(p.Refused):p.temp_path(name)
        self.assertEqual(p.temp_path('a'*16),'/sdcard/Download/.bh-app01-ph03-'+'a'*16+'.xml')
        for txt in ['[0,0][0,200]','[0,0][9000,200]','[1,1][3,2];oops']:
            with self.subTest(bounds=txt),self.assertRaises(p.Refused):
                p.center(ET.Element('node',{'bounds':txt}))

    def test_navigation_unique_lower_footer(self):
        nodes=p.own_tree(hierarchy(show='rules'))
        self.assertEqual(p.find_nav_tab(nodes,'rules'),(315,1915))
        self.assertTrue(p.visible_marker(nodes,'rules'))
        self.assertFalse(p.visible_marker(nodes,'apps'))
        with self.assertRaises(p.Refused):p.find_nav_tab(nodes,'not-an-option')
        nodes.append(ET.Element('node',{'text':'Rules','bounds':'[25,1850][200,1980]'}))
        with self.assertRaises(p.Refused):p.find_nav_tab(nodes,'rules')
        nodes.pop()
        nodes=[n for n in nodes if n.get('text')!='Rules']
        with self.assertRaises(p.Refused):p.find_nav_tab(nodes,'rules')

    def test_no_forged_or_malformed_ui_hierarchy(self):
        for bad in [b'',b'<foo />',b'<hierarchy><broken',b'A'*1000001]:
            with self.subTest(data=bad[:20]),self.assertRaises(p.Refused):p.own_tree(bad)
        nodes=p.own_tree(hierarchy(show='more'))
        self.assertTrue(p.visible_marker(nodes,'more'))

    def test_resumed_foreground_only(self):
        self.assertEqual(p.focused_package('topResumedActivity=ActivityRecord{ab u0 '+p.APP+'/.MainActivity t9}'),p.APP)
        self.assertEqual(p.focused_package('mResumedActivity: ActivityRecord{ab u0 '+p.PICKER_PACKAGES[0]+'/.files.FilesActivity t9}'),p.PICKER_PACKAGES[0])
        self.assertIsNone(p.focused_package('Task{ history='+p.APP+'/.MainActivity }'))
        self.assertIsNone(p.focused_package('topResumedActivity=ActivityRecord{abc u0 com.other.app/.MainActivity}'))

    def test_acks_are_distinct_for_readonly_and_ui(self):
        self.assertNotEqual(p.ACK,p.READ_ACK)
        self.assertNotEqual(p.ACK,p.ph02.ACK)
        self.assertNotIn('I_AUTHORIZE_ROOT',p.ACK)

    def test_navigation_journey_taps_only_known_footer(self):
        labels=['home','rules','apps','more','home']
        class SyntheticSession:
            def __enter__(self):self.index=0;return self
            def __exit__(self,*args):self.cleaned=True
            def snapshot(self):
                label=labels[min(self.index,len(labels)-1)]
                raw=hierarchy(show=label)
                return p.own_tree(raw),p.hashlib.sha256(raw).hexdigest()
        taps=[]
        def tap(x,y,s):taps.append((x,y));s.index+=1
        with patch.object(p,'require_target'),patch.object(p,'start_ui'),\
             patch.object(p,'focus',return_value=p.APP),\
             patch.object(p,'Session',SyntheticSession),patch.object(p,'safe_tap',side_effect=tap):
            result=p.navigation_journey()
        self.assertEqual(result['navigation_pages'],labels)
        self.assertEqual(len(taps),4)
        self.assertTrue(result['device_temp_xml_cleanup'])

    def test_saf_cancel_requires_actual_picker_then_resume(self):
        values=[p.APP,p.PICKER_PACKAGES[1],p.APP]
        ops=[]
        with patch.object(p,'require_target'),patch.object(p,'start_ui'),\
             patch.object(p,'focus',side_effect=values),patch.object(p,'adb',side_effect=lambda argv,**kw:(ops.append(argv) or FakeResult())),\
             patch.object(p.time,'sleep'):
            r=p.saf_cancel_journey(timeout_seconds=5)
        self.assertTrue(r['saf_picker_cancelled'])
        self.assertFalse(r['file_imported'])
        self.assertEqual(ops,[['shell','input','keyevent','KEYCODE_BACK']])

    def test_saf_refuses_when_user_never_opens_picker(self):
        calls=[p.APP,p.APP,p.APP]
        with patch.object(p,'require_target'),patch.object(p,'start_ui'),\
             patch.object(p,'focus',side_effect=calls),patch.object(p.time,'monotonic',side_effect=[0,0,1,2,99]),\
             patch.object(p.time,'sleep'),self.assertRaises(p.Refused):
            p.saf_cancel_journey(timeout_seconds=4)

    def test_hosted_and_physical_not_blended(self):
        source=(HERE/'scripts/ci/bh_app01_p07_ph03.py').read_text()
        self.assertIn("'physical_android16_qualified':False",source)
        self.assertIn("'release_qualified':False",source)
        self.assertIn('hosted_apk_matches_installed',source)
        self.assertIn('ph02.verified_hosted',source)
        self.assertNotIn("['shell','su'",source)
        self.assertNotIn("['install'",source)

    def test_qs_duplicate_cancel_real_dialog(self):
        before=hierarchy(show='home',modal=True)
        after=hierarchy(show='home',modal=False)
        class TestSession:
            def __enter__(self):self.path=p.temp_path('b'*16);self.calls=0;return self
            def __exit__(self,*args):return False
            def snapshot(self):
                self.calls+=1
                v=before if self.calls==1 else after
                return p.own_tree(v),p.hashlib.sha256(v).hexdigest()
        acts=[]
        def fake_adb(parts,**kwargs):
            acts.append(parts)
            if parts[:3]==['shell','am','start']:return FakeResult(b'Status: ok\n')
            if parts[:2]==['exec-out','cat']:return FakeResult(before)
            return FakeResult()
        with patch.object(p,'require_target'),patch.object(p,'Session',TestSession),\
             patch.object(p,'adb',side_effect=fake_adb),patch.object(p,'focus',return_value=p.APP),\
             patch.object(p.time,'sleep'):
            result=p.qs_duplicate_cancel_journey()
        self.assertEqual(result['qs_intents_delivered'],2)
        self.assertTrue(result['only_cancel_tapped'])
        self.assertFalse(result['hosts_update_triggered_by_runner'])
        self.assertEqual(len([x for x in acts if x[:3]==['shell','input','tap']]),1)
        self.assertEqual(len([x for x in acts if x[:3]==['shell','am','start']]),2)

    def test_never_tap_update_button(self):
        script=(HERE/'scripts/ci/bh_app01_p07_ph03.py').read_text()
        self.assertIn('from bh_app01_p07_qs_hierarchy import parse as parse_qs',script)
        self.assertIn("['shell','input','keyevent','KEYCODE_BACK']",script)
        self.assertIn('real QS',script)
        self.assertNotIn('adb install',script)
        self.assertNotIn('update-start',script)

if __name__=='__main__':unittest.main()
