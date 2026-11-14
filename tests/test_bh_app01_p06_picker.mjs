import assert from 'node:assert/strict';
import {injectSafPicker, companionSafPickerPlugin} from '../webui/runtime/companion_saf_picker.mjs';
import {nativeAppTransport, validateReply, kernelSuTransport} from '../webui/runtime/companion_transport.mjs';

const legitimate='/storage/emulated/0/Android/data/com.mikeyphw.bindhosts/cache/imports/bh-pick-012345abcdef-safe_host.txt';
const valid={api:6,action:'pick-text',path:legitimate};
assert.equal(validateReply('pick-text',valid).path,legitimate);
for (const path of [
  '/sdcard/Download/custom.txt',
  '/storage/emulated/0/Download/custom.txt',
  '/storage/emulated/0/Android/data/com.mikeyphw.bindhosts/cache/imports/../../bad.txt',
  legitimate+';reboot',
  'file:///storage/emulated/0/Android/data/com.mikeyphw.bindhosts/cache/imports/bh-pick-012345abcdef-safe_host.txt',
  legitimate.replace('012345abcdef','NONCE-INJECT'),
  legitimate.replace('safe_host.txt','bad\nname.txt'),
]) assert.throws(()=>validateReply('pick-text',{...valid,path}),path);
for(const body of [{...valid,api:5},{...valid,action:'status'},{...valid,extra:true},{...valid,path:undefined}])
  assert.throws(()=>validateReply('pick-text',body));

const calls=[];
globalThis.window={BindhostsBridge:{postMessage(raw){
  const request=JSON.parse(raw);calls.push(request);
  this.onmessage({data:JSON.stringify({id:request.id,ok:true,value:valid})});
}}};
const shim=await import('../webui/runtime/companion_kernelsu_alt.mjs');
assert.equal(typeof window.__bhCompanionPickText,'function');
assert.equal(await shim.pickCompanionTextFile(),legitimate);
assert.deepEqual(Object.keys(calls[0]).sort(),['id','op']);
assert.equal(calls[0].op,'pick-text');
assert.throws(()=>nativeAppTransport(window.BindhostsBridge).invoke('pick-text','/sdcard/Download/data.txt'));
const kernel=kernelSuTransport(async()=>({errno:0,stdout:JSON.stringify(valid)}));
await assert.rejects(kernel.invoke('pick-text'));

const badBridge={postMessage(raw){let r=JSON.parse(raw);this.onmessage({data:JSON.stringify({id:r.id,ok:false})});}};
await assert.rejects(nativeAppTransport(badBridge).invoke('pick-text'));

const original="export const FileSelector = { getFilePath: async function (type) {\n return 'untrusted'; } };";
const transformed=injectSafPicker(original);
assert.equal(transformed.includes("window.__bhCompanionPickText()"),true);
assert.equal(transformed.includes("type === 'txt'"),true);
assert.equal((transformed.match(/getFilePath:/g)||[]).length,1);
assert.throws(()=>injectSafPicker('export const FileSelector = {};'));
assert.throws(()=>injectSafPicker(original+original));
const plugin=companionSafPickerPlugin();
assert.equal(plugin.enforce,'pre');
assert.equal(plugin.transform(original,'/repo/webui/route.js'),null);
assert.equal(plugin.transform(original,'/repo/webui/utils/file_selector.js').code,transformed);
assert.equal(plugin.transform(original,'/repo/webui/utils/file_selector.js?cache').code,transformed);
assert.equal((await shim.exec('am start -a android.settings.SECURITY_SETTINGS')).errno,13);
assert.equal((await shim.exec('cat /sdcard/Download/passwords.txt')).errno,13);
assert.equal(calls.length,1,'invalid shell/clipboard commands never cross native bridge');
console.log('BH_APP01_P06_SAF_PICKER_PASS accepted=1 denied=11 transform=PASS kernel_webui=UNCHANGED');
