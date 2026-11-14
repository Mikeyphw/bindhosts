import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import {exec,moreCommand} from '../webui/runtime/companion_kernelsu_alt.mjs';
import {validateReply,validPageRequest,nativeAppTransport} from '../webui/runtime/companion_transport.mjs';
if(!globalThis.crypto?.subtle)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
const MOD='/data/adb/modules/bindhosts';
const id='bh-20261114T181234-AbC123';
const archive=`bindhosts-backup-${id}.tar`;
const cases=[
  [`sh ${MOD}/config_backup_safe.sh status`,'backup','status',true],
  [`sh ${MOD}/config_backup_safe.sh health`,'backup','health',true],
  [`sh ${MOD}/config_backup_safe.sh list`,'backup','list',true],
  [`sh ${MOD}/config_backup_safe.sh imports`,'backup','imports',true],
  [`sh ${MOD}/config_backup_safe.sh verify ${id}`,'backup',`verify~${id}`,true],
  [`sh ${MOD}/config_backup_safe.sh preview ${id}`,'backup',`preview~${id}`,true],
  [`sh ${MOD}/config_backup_safe.sh create`,'backup','create',false],
  [`sh ${MOD}/config_backup_safe.sh restore ${id}`,'backup',`restore~${id}`,false],
  [`sh ${MOD}/config_backup_safe.sh export ${id}`,'backup',`export~${id}`,false],
  [`sh ${MOD}/config_backup_safe.sh import ${archive}`,'backup',`import~${archive}`,false],
  [`sh ${MOD}/ux05_diagnostics.sh status`,'diagnostics','status',true],
  [`sh ${MOD}/ux05_diagnostics.sh history 100`,'diagnostics','history~100',true],
  [`sh ${MOD}/ux05_diagnostics.sh export`,'diagnostics','export',false],
  [`sh ${MOD}/bindhosts.sh --response status`,'response','status',true],
  [`sh ${MOD}/bindhosts.sh --response set logo`,'response','set~logo',false],
  [`sh ${MOD}/bindhosts.sh --response https enable`,'response','https~enable',false],
];
const calls=[];const output='BH_APP01_MORE_RECEIPT_PASS';
globalThis.window={BindhostsBridge:{postMessage(raw){
  const req=JSON.parse(raw);calls.push(req);
  const [source,selector,offset,expected]=(req.arg||'').split('|');
  const sha=createHash('sha256').update(output).digest('hex');
  const value=req.op==='read-page'?{api:4,action:'read-page',source,selector,offset:Number(offset),next:null,
    size:Buffer.byteLength(output),sha256:sha,encoded:Buffer.from(output).toString('base64')}:
    {api:5,action:req.op,encoded:Buffer.from(output).toString('base64')};
  this.onmessage({data:JSON.stringify({id:req.id,ok:true,value})});
}}};
for(const [cmd,op,arg,paged] of cases){
  assert.deepEqual(moreCommand(cmd),{op,arg});
  if(paged)assert(validPageRequest(`${op}|${arg}|0|none`));
  const response=await exec(cmd);
  assert.equal(response.errno,0,cmd);assert.equal(response.stdout,output);
  assert.equal(calls.at(-1).op,paged?'read-page':op);
}
const invalid=[
  `sh ${MOD}/config_backup_safe.sh restore ../etc/passwd`,
  `sh ${MOD}/config_backup_safe.sh import /sdcard/hijack.tar`,
  `sh ${MOD}/config_backup_safe.sh restore ${id};reboot`,
  `sh ${MOD}/ux05_diagnostics.sh history 101`,
  `sh ${MOD}/ux05_diagnostics.sh append anything`,
  `sh ${MOD}/bindhosts.sh --response https install`,
  `sh ${MOD}/bindhosts.sh --response set logo;reboot`,
  'am start -a android.settings.SECURITY_SETTINGS',
  'svc power reboot || reboot',
];
for(const cmd of invalid){const before=calls.length;assert.equal(moreCommand(cmd),null);assert.equal((await exec(cmd)).errno,13);assert.equal(calls.length,before)}
assert.throws(()=>nativeAppTransport(window.BindhostsBridge).invoke('backup','restore~../bad'));
assert.throws(()=>nativeAppTransport(window.BindhostsBridge).invoke('read-page','backup|restore~'+id+'|0|none'));
assert.throws(()=>validateReply('backup',{api:5,action:'backup',encoded:'!!!'}));
console.log(`BH_APP01_P04B_P03_MORE_PASS positive=${cases.length} denied=${invalid.length}`);
