import assert from 'node:assert/strict';
import { nativeAppTransport, kernelSuTransport, validateReply } from '../webui/runtime/companion_transport.mjs';
import {exec, P04_COMMANDS, P05_COMMANDS} from '../webui/runtime/companion_kernelsu_alt.mjs';
const values = {
  hello: {api:1,module:'bindhosts',versionCode:21611,capabilities:['hello','status']},
  status: {api:1,hosts:'ACTIVE',operation:'IDLE'},
  pause: {api:2,action:'pause',hosts:'PAUSED',verified:true},
  resume: {api:2,action:'resume',hosts:'ACTIVE',verified:true},
  'update-start': {api:2,action:'update-start',operation:'RUNNING',accepted:true},
  'update-status': {api:2,action:'update-status',operation:'RUNNING',step:'DOWNLOADING',receipt:'NONE'},
  'update-events': {api:2,action:'update-events',encoded: Buffer.from('DOWNLOADING|Source 1 validated').toString('base64')},
};
const calls=[];
globalThis.window = {BindhostsBridge:{postMessage(raw){const req=JSON.parse(raw); calls.push(req.op);this.onmessage({data:JSON.stringify({id:req.id,ok:true,value:values[req.op]})});}}};
assert.equal(P04_COMMANDS.length,2);
assert.equal(P05_COMMANDS.length,5);
for(const action of ['pause','resume','update-start','update-status','update-events']) {
  assert.equal(validateReply(action,values[action]).api,2);
}
for(const [op, invalid] of [
  ['pause',{api:2,action:'pause',hosts:'ACTIVE',verified:true}],
  ['resume',{api:2,action:'resume',hosts:'ACTIVE',verified:false}],
  ['update-start',{api:2,action:'update-start',operation:'FAILED',accepted:true}],
  ['update-status',{api:2,action:'update-status',operation:'DONE',receipt:'NONE',step:'NONE'}],
  ['update-events',{api:2,action:'update-events',encoded:'x;rm -rf /'}],
]) assert.throws(()=>validateReply(op,invalid));
assert.equal((await exec(P05_COMMANDS[0])).stdout,'BH_HOSTS_PAUSE_PASS\nBH_HOSTS_STATE=PAUSED\n');
assert.equal((await exec(P05_COMMANDS[1])).stdout,'BH_HOSTS_RESUME_PASS\nBH_HOSTS_STATE=ACTIVE\n');
assert.match((await exec(P05_COMMANDS[2])).stdout,/^BH_UX09_STARTED=1\n$/);
assert.match((await exec(P05_COMMANDS[3])).stdout,/^BH_UX09_STATE=RUNNING\nBH_UX09_STEP=DOWNLOADING\n$/);
assert.equal((await exec(P05_COMMANDS[4])).stdout,'DOWNLOADING|Source 1 validated');
const previous=calls.length;
for(const injected of [
  P05_COMMANDS[0]+';touch /tmp/bad', P05_COMMANDS[0]+' ', P05_COMMANDS[2]+' &',
  'sh /data/adb/modules/bindhosts/bindhosts.sh --force-update',
  'sh /data/adb/modules/bindhosts/bindhosts.sh tracker json rules',
  'sh /data/adb/modules/bindhosts/hosts_operation_ux09.sh worker',
  'pm list packages -3', null, {},
]) {
  const answer=await exec(injected);
  assert.equal(answer.errno,13,`must refuse ${String(injected)}`);
}
assert.equal(calls.length,previous,'unsafe native invocation');
const kernel=kernelSuTransport(async()=>({errno:0,stdout:JSON.stringify(values.status)}));
await assert.rejects(kernel.invoke('pause'));
assert.throws(()=>nativeAppTransport(window.BindhostsBridge).invoke('reboot'));
console.log('BH_APP01_P05_EXACT_COMMAND_GATE_PASS host_actions=5 denied=9');
