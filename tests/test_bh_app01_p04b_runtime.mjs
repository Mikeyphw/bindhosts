import assert from 'node:assert/strict';
import {exec, managementCommand} from '../webui/runtime/companion_kernelsu_alt.mjs';
import {nativeAppTransport,validateReply} from '../webui/runtime/companion_transport.mjs';
const mod='/data/adb/modules/bindhosts';
const sample='BH_UX09_BATCH_APPLIED';
const calls=[];
globalThis.window={BindhostsBridge:{postMessage(raw){const req=JSON.parse(raw);calls.push(req);this.onmessage({data:JSON.stringify({id:req.id,ok:true,value:{api:3,action:req.op,encoded:Buffer.from(sample).toString('base64')}})});}}};
for(const [command,op,arg] of [
  [`sh ${mod}/source_catalog.sh status`,'catalog','status'],
  [`sh ${mod}/source_catalog_batch_ux09.sh batch adaway,energized-basic`,'catalog','batch|adaway,energized-basic'],
  [`sh ${mod}/hosts_config_safe.sh add sources aHR0cHM6Ly9leGFtcGxlLm9yZw==`,'config-write','add|sources|aHR0cHM6Ly9leGFtcGxlLm9yZw=='],
  [`sh ${mod}/bindhosts.sh tracker json status`,'tracker','status'],
  [`sh ${mod}/bindhosts.sh tracker preview org.example.client`,'tracker','preview|org.example.client'],
  [`sh ${mod}/bindhosts.sh tracker enroll org.example.client`,'tracker','enroll|org.example.client'],
  ['pm list packages -3','packages','user'],
  ['cat "/data/adb/bindhosts/whitelist.txt"','config-read','whitelist'],
]){
  assert.deepEqual(managementCommand(command),{op,arg});
  const result=await exec(command);
  assert.equal(result.errno,0,command);
  assert.equal(result.stdout,sample);
}
for(const command of [
  `sh ${mod}/bindhosts.sh tracker enroll org.example.client;reboot`,
  `sh ${mod}/bindhosts.sh tracker monitor reset`,
  `sh ${mod}/hosts_config_safe.sh add sources x;rm`,
  `sh ${mod}/hosts_config_safe.sh stage-commit anything whitelist`,
  'cat "/etc/shadow"',
  'pm list packages -3 --user 0',
  `sh ${mod}/source_catalog_batch_ux09.sh batch adaway,$(id)`,
  `sh ${mod}/source_catalog_batch_ux09.sh batch adaway,adaway;`,
  'svc power reboot || reboot',
]){
  const old=calls.length;
  assert.equal(managementCommand(command),null,command);
  const response=await exec(command);
  assert.equal(response.errno,13,command);
  assert.equal(calls.length,old,command);
}
assert.throws(()=>nativeAppTransport(window.BindhostsBridge).invoke('tracker','bad;cat /etc/shadow'));
assert.throws(()=>validateReply('tracker',{api:3,action:'tracker',encoded:'%%%'}));
assert.throws(()=>nativeAppTransport(window.BindhostsBridge).invoke('tracker'));
console.log('BH_APP01_P04B_EXACT_COMMANDS_PASS allowed=8 denied=9');
