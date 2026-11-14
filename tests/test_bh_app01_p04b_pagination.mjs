import assert from 'node:assert/strict';
import { webcrypto, createHash } from 'node:crypto';
import {exec,readPaginated} from '../webui/runtime/companion_kernelsu_alt.mjs';
import {validateReply,nativeAppTransport} from '../webui/runtime/companion_transport.mjs';
if (!globalThis.crypto?.subtle) Object.defineProperty(globalThis,"crypto",{value:webcrypto, configurable:true});
const text=('línea\n'.repeat(800)+'🦊end\n');
const bytes=Buffer.from(text,'utf8');
assert(bytes.length>4800);
const sha=createHash('sha256').update(bytes).digest('hex');
const calls=[];
let changed=false;
let corrupt=false;
const bridge={postMessage(raw){
  const req=JSON.parse(raw);
  calls.push(req);
  assert.equal(req.op,'read-page');
  const [source,selector,offsetText,expected]=req.arg.split('|');
  const offset=Number(offsetText);
  assert.equal(source,'config-read');
  assert.equal(selector,'sources');
  assert(expected==='none'||expected===sha);
  const data=bytes.subarray(offset,offset+3072);
  const body={api:4,action:'read-page',source,selector,offset,
    next:offset+data.length===bytes.length?null:offset+data.length,
    size:bytes.length,sha256:changed?'f'.repeat(64):sha,
    encoded:Buffer.from(data).toString('base64')};
  if(corrupt)body.encoded=Buffer.from(data).fill(0).toString('base64');
  this.onmessage({data:JSON.stringify({id:req.id,ok:true,value:body})});
}};
globalThis.window={BindhostsBridge:bridge};
const result=await exec('cat "/data/adb/bindhosts/sources.txt"');
assert.equal(result.errno,0);
assert.equal(result.stdout,text);
assert(calls.length>1);
assert.equal(calls[0].arg,'config-read|sources|0|none');
assert.equal(calls[1].arg.split('|')[3],sha);
changed=true;
let rejected=await exec('cat "/data/adb/bindhosts/sources.txt"');
assert.equal(rejected.errno,13);
changed=false;corrupt=true;
rejected=await exec('cat "/data/adb/bindhosts/sources.txt"');
assert.equal(rejected.errno,13);
const before=calls.length;
assert.equal((await exec('cat "/etc/shadow"')).errno,13);
assert.equal(calls.length,before);
assert.throws(()=>nativeAppTransport(bridge).invoke('read-page','tracker|enroll~org.test|0|none'));
assert.throws(()=>validateReply('read-page',{api:4,action:'read-page',source:'config-read',selector:'sources',offset:0,next:200,size:200,sha256:sha,encoded:'a'}));
console.log('BH_APP01_P04B_P02_PAGING_PASS pages='+calls.length+' digest-and-drift=REFUSED unsafe-command=REFUSED');
