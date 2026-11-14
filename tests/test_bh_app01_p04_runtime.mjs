import assert from 'node:assert/strict';
import { exec, spawn, P04_COMMANDS } from '../webui/runtime/companion_kernelsu_alt.mjs';

const invocations=[];
globalThis.window = {
  BindhostsBridge: {
    postMessage(raw) {
      const req=JSON.parse(raw);
      invocations.push(req);
      const values={
        hello:{api:1,module:'bindhosts',versionCode:21611,capabilities:['hello','status']},
        status:{api:1,hosts:'ACTIVE',operation:'IDLE'}
      };
      this.onmessage({data:JSON.stringify({id:req.id,ok:true,value:values[req.op]})});
    },
  },
};
assert.equal(P04_COMMANDS.length,2);
let r=await exec(P04_COMMANDS[0]);
assert.equal(r.errno,0);
assert.equal(r.stdout,'BH_HOSTS_STATE=ACTIVE\n');
r=await exec(P04_COMMANDS[1]);
assert.equal(r.errno,0);
assert.match(r.stdout,/versionCode 21611/);
assert.match(r.stdout,/module read-back, not DNS proof/);
assert.deepEqual(invocations.map(x=>x.op),['status','hello','status']);
for(const command of [
  'sh /data/adb/modules/bindhosts/bindhosts.sh --hosts-control update',
  'sh /data/adb/modules/bindhosts/bindhosts.sh tracker json status;id',
  'pm list packages -3;id',
  'sh /data/adb/modules/bindhosts/bindhosts.sh tracker preview com.example.app;id',
  'sh /data/adb/modules/bindhosts/hosts_operation_ux09.sh worker',
  'cat "/data/adb/modules/bindhosts/module.prop";touch /tmp/unwanted',
  'sh /data/adb/modules/bindhosts/bindhosts.sh --setup-link',
  'svc power reboot || reboot',
  '', null, {},
]) {
  const before=invocations.length;
  const denied=await exec(command);
  assert.equal(denied.errno,13,`fail closed: ${String(command)}`);
  assert.equal(invocations.length,before,'unexpected native bridge call');
}
assert.throws(()=>spawn('sh',['--force-update']),/P05_REFUSED/);
console.log('BH_APP01_P04_COMMAND_GATE_PASS read=2 writes_refused=11');
// The same UX10 navigation/back contract must be reachable from Android Back.
const { WXEventHandler } = await import('../webui/runtime/companion_webuix.mjs');
let backCount=0;
const handlers=new Map();
window.addEventListener=(key,callback)=>handlers.set(key,callback);
window.dispatchEvent=(event)=>handlers.get(event.type)?.(event);
globalThis.document={
  querySelector:()=>({id:'page-hosts'}),
  querySelectorAll:()=>[],
  getElementById:()=>null,
};
new WXEventHandler().on(window,'back',()=>{backCount++;});
assert.equal(window.__bhCompanionBack(),true);
assert.equal(backCount,1);
document.querySelector=()=>({id:'page-home'});
assert.equal(window.__bhCompanionBack(),false);
assert.equal(backCount,1);
console.log('BH_APP01_P04_ANDROID_BACK_ROUTING_PASS');
