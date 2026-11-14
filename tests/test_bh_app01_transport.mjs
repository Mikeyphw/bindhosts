import assert from 'node:assert/strict';
import {kernelSuTransport, nativeAppTransport, validateReply} from '../webui/runtime/companion_transport.mjs';
const status = {api:1,hosts:'ACTIVE',operation:'IDLE'};
const hello = {api:1,module:'bindhosts',versionCode:21611,capabilities:['hello','status']};
assert.equal(validateReply('status', status).hosts, 'ACTIVE');
for (const x of [null, {}, {api:1,hosts:'ACTIVE',operation:'COMPLETE'}, {api:2,hosts:'ACTIVE',operation:'IDLE'}]) {
  assert.throws(() => validateReply('status', x));
}
let called = [];
const kernel = kernelSuTransport(async cmd => {called.push(cmd);return {errno:0,stdout:JSON.stringify(status)};});
assert.deepEqual(await kernel.invoke('status'), status);
assert.deepEqual(called, ['sh /data/adb/modules/bindhosts/companion_api.sh status']);
await assert.rejects(kernel.invoke('pause'));
assert.throws(() => kernelSuTransport(() => {},'/tmp/evil'));
const bridge = {postMessage(data) { const request = JSON.parse(data); this.onmessage({data:JSON.stringify({id:request.id,ok:true,value:request.op === 'hello' ? hello : status})}); }};
const native = nativeAppTransport(bridge);
assert.deepEqual(await native.invoke('hello'),hello);
assert.deepEqual(await native.invoke('status'),status);
assert.throws(() => native.invoke('update'));
const refusing = {postMessage(data) { const {id} = JSON.parse(data); this.onmessage({data: JSON.stringify({id,ok:false})}); }};
await assert.rejects(nativeAppTransport(refusing).invoke('status'));
console.log('BH_APP01_TRANSPORT_SOURCE_TESTS_PASS');
