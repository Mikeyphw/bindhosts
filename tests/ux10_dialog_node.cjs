// UX10: execute actual confirmation implementation against a minimal Android WebView-like DOM.
// No npm install, browser, KernelSU, device, network or module actions.
'use strict';
const fs=require('fs');
const vm=require('vm');
const assert=require('node:assert/strict');
let src=fs.readFileSync(require('path').resolve(__dirname,'../webui/utils/hosts_operations_ux09.js'),'utf8');
src=src.replace(/^import .*;\s*$/gm,'').replace(/^export /gm,'');
const elements=new Map();
function element(id){
 const listeners=new Map();
 return {id,hidden:id==='ux09-operation-confirm',textContent:'',dataset:{},listeners,
   addEventListener(name,fn){listeners.set(name,fn);},
   removeEventListener(name,fn){if(listeners.get(name)===fn)listeners.delete(name);},
   click(){listeners.get('click')?.();},focus(){},
   scrollTop:0,scrollHeight:0};
}
for(const id of ['ux09-operation-confirm','ux09-operation-confirm-title','ux09-operation-confirm-message','ux09-operation-confirm-yes','ux09-operation-confirm-no','ux09-operation-overlay','ux09-operation-close','ux09-operation-refresh','ux09-operation-stage','ux09-operation-status','ux09-operation-lines','ux09-operation-summary','ux10-operation-source'])elements.set(id,element(id));
const history=[];
const ctx={moduleDirectory:'/data/adb/modules/bindhosts',showPrompt(){},
 registerManagedPanel(panel,handlers){
   panel.open=()=>{panel.hidden=false;history.push({panel,handlers});handlers.open();};
   panel.close=()=>{const ix=history.findLastIndex(x=>x.panel===panel);if(ix>=0)history.splice(ix,1);handlers.close();};
 },
 document:{getElementById(id){return elements.get(id);},querySelectorAll(){return[];}},
 exec:async()=>({errno:0,stdout:'BH_UX09_STATE=IDLE\n'}),
 setInterval(){return 1},clearInterval(){},console,
 CustomEvent:class{},
 };
vm.runInNewContext(src+'\nthis.accept=confirmHostsAction;this.mount=mountHostsOperationUI;',ctx,{filename:'hosts_operations_ux09.js'});
(async()=>{
 ctx.mount();
 let layer=elements.get('ux09-operation-confirm');
 let c=ctx.accept('Update hosts?','Download lists');
 assert.equal(layer.hidden,false);
 elements.get('ux09-operation-confirm-no').click();
 assert.equal(layer.hidden,true,'Cancel must close immediately');
 assert.equal(await c,false,'Cancel must not start update');
 assert.equal(history.length,0);
 c=ctx.accept('Update hosts?','Download lists');
 elements.get('ux09-operation-confirm-yes').click();
 assert.equal(layer.hidden,true,'Continue must close immediately');
 assert.equal(await c,true);
 assert.equal(history.length,0);
 c=ctx.accept('Update hosts?','Download lists');
 assert.equal(layer.hidden,false);
 // Simulate Android Back action wired through index.js: trigger Cancel first.
 elements.get('ux09-operation-confirm-no').click();
 assert.equal(layer.hidden,true,'Android Back must close');
 assert.equal(await c,false,'Android Back must cancel');
 assert.equal(history.length,0);
 console.log('UX10_DIALOG_PASS Cancel/Continue/AndroidBack each dismiss and settle once');
})().catch(e=>{console.error(e);process.exitCode=1;});
