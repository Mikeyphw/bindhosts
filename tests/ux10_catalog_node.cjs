// UX10 HF01: execute real catalog functions with deterministic in-memory WebView DOM.
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const presets=[{id:'adaway',name:'AdAway',group:'core',level:'Baseline',description:'AdAway',url:'https://adaway.org/hosts.txt'},
{id:'cubic',name:'Cubic',group:'comprehensive',level:'Comprehensive',description:'Cubic',url:'https://example.com/cubic'},
{id:'energized-spark',name:'Spark',group:'energized',level:'Lightweight',description:'Spark',url:'https://energized.pro/spark/hosts.txt'},
{id:'energized-blu',name:'Blu',group:'energized',level:'Balanced',description:'Blu',url:'https://energized.pro/blu/hosts.txt'},
{id:'energized-ultimate',name:'Ultimate',group:'energized',level:'Aggressive',description:'Ultimate',url:'https://energized.pro/ultimate/hosts.txt'}];
function el(tag='div'){
  const props=new Map(),handlers=new Map();
  return {tagName:tag.toUpperCase(),children:[],textContent:'',hidden:false,checked:false,disabled:false,href:'',
    classList:{add(){}},setAttribute(n,v){props.set(n,v);},getAttribute(n){return props.get(n);},
    addEventListener(n,fn){handlers.set(n,fn);},replaceChildren(...children){this.children=children;},
    append(...children){this.children.push(...children);},toggleAttribute(n,state){this[n]=state;},
    closest(){return null;},click(){this.checked=this.type==='radio' ? true : !this.checked;this.onchange?.();handlers.get('click')?.({target:this});},
    querySelector(){return null;}};
}
const ids=['#ux09-core','#ux09-comprehensive','#ux09-energized','#ux09-tab-presets','#ux09-tab-mine','#ux09-tab-advanced',
'#ux09-presets','#ux09-mine','#ux09-advanced','#catalog-save','#catalog-update','#catalog-status','#catalog-view-log',
'#ux10-sources-back','#ux09-open-rules','#ux09-open-more','#ux09-manual-list'];
const elements=new Map(ids.map(id=>[id,el()]));
const root={querySelector(sel){return elements.get(sel)||null;}};
const events=[];let confirmAnswer=false,confirmCount=0,backendCalls=0,manualEdits=0;
const catalogStatus='adaway|on\ncubic|off\nenergized-spark|off\nenergized-blu|on\nenergized-ultimate|off\n';
const ctx={__presets:presets,moduleDirectory:'/fake/module',document:{createElement:el,addEventListener(){}},
  exec:async command=>{backendCalls++;return {errno:0,stdout:command.includes('applied-status')?'BH_UX09_APPLIED=CURRENT\n':command.includes('manual-list')?'MANUAL|on|https://example.org/user\n':catalogStatus}},
  router:{navigate(name){events.push('navigate:'+name)}},showPrompt(s){events.push('prompt:'+s)},
  confirmHostsAction:async()=>{confirmCount++;return confirmAnswer;},secureToggle:async()=>{manualEdits++;},
  beginHostsUpdate:async()=>{},showHostsOperation:()=>{},console};
let src=fs.readFileSync(path.resolve(__dirname,'../webui/page/catalog/catalog.js'),'utf8');
src=src.replace(/^import .*;\s*$/gm,'').replace(/export \{mount,onShow,onHide\};?/g,'').replace(/^export /gm,'');
src='const presets=__presets;\n'+src+'\nthis.ux10={mount,onShow,hasPendingSourceChanges,approveSourceExit};';
vm.runInNewContext(src,ctx,{filename:'catalog.js'});
(async()=>{
 ctx.ux10.mount(root);ctx.ux10.onShow();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ctx.ux10.hasPendingSourceChanges(),false);
 const energy=elements.get('#ux09-energized');assert.equal(energy.children.length,4,'None + three Ener tiers');
 assert.equal(energy.children[0].children[1].type,'radio');
 assert.equal(energy.children[0].children[1].checked,false,'Blu initially selected');
 const spark=energy.children[1].children[1];spark.checked=true;spark.onchange();
 assert.equal(ctx.ux10.hasPendingSourceChanges(),true);
 const after=elements.get('#ux09-energized');
 assert.equal(after.children[1].children[1].checked,true,'Spark chosen');
 assert.equal(after.children[2].children[1].checked,false,'Blu deselected');
 ctx.ux10.onShow();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(elements.get('#ux09-energized').children[1].children[1].checked,true,'unsaved selection survives refresh');
 confirmAnswer=false;assert.equal(await ctx.ux10.approveSourceExit(),false,'Cancel keeps changes');
 assert.equal(ctx.ux10.hasPendingSourceChanges(),true);
 confirmAnswer=true;assert.equal(await ctx.ux10.approveSourceExit(),true,'explicit discard allows navigation');
 assert.equal(ctx.ux10.hasPendingSourceChanges(),false,'confirmed discard must actually discard edits');
 const none=elements.get('#ux09-energized').children[0].children[1];none.checked=true;none.onchange();
 assert.equal(elements.get('#ux09-energized').children[0].children[1].checked,true,'None is selectable');
 const before=manualEdits;
 elements.get('#ux09-tab-mine').addEventListener; // documented internal tab exists
 // Guard a manual action from destroying a pending curated selection.
 const source=elements.get('#ux09-manual-list');
 elements.get('#ux09-tab-mine').click();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(source.children.length,1);
 const action=source.children[0].children[1];await action.onclick();
 assert.equal(manualEdits,before,'dirty preset selection prevents manual toggle');
 assert.equal(ctx.ux10.hasPendingSourceChanges(),true);
 assert.ok(confirmCount>=2);
 console.log('UX10_CATALOG_BEHAVIOR_PASS exclusive-radio/None/dirty-exit/save-preservation/manual-guard');
})().catch(e=>{console.error(e);process.exitCode=1;});
