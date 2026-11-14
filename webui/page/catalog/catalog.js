// UX09: staged, atomic source selection with applied-vs-configured distinction.
import { exec } from 'kernelsu-alt';
import { secureToggle } from '../../utils/hosts_secure_io.js';
import { router } from '../../route.js';
import { moduleDirectory, showPrompt } from '../../utils/util.js';
import { beginHostsUpdate, showHostsOperation, confirmHostsAction } from '../../utils/hosts_operations_ux09.js';
import presets from '../../catalog-presets.json';

let view;
let states = new Map(), selected = new Set();
let original = new Set(), busy = false, applied = 'UNKNOWN', lastApplied = null;
const IDS = new Set(presets.map(p => p.id));
const ROOT = `sh ${moduleDirectory}/source_catalog.sh`;
const BATCH = `sh ${moduleDirectory}/source_catalog_batch_ux09.sh`;
function el(tag, className, content) {
  const x = document.createElement(tag); if (className) x.className = className;
  if (content !== undefined) x.textContent = content; return x;
}
async function call(command) {
  const r = await exec(command);
  if (r?.errno !== 0) throw new Error(`Source operation refused (exit ${r?.errno ?? 'unknown'})`);
  return String(r.stdout ?? '').trim();
}
function dirty() { return [...new Set([...selected,...original])].some(id => selected.has(id) !== original.has(id)); }
function setStatus(message) { const x = view?.querySelector('#catalog-status'); if (x) x.textContent = message; }
function makeChoice(p) {
  const state = states.get(p.id) || 'off';
  const line = el('div', 'ux-card ux09-preset');
  const info = el('div', 'ux09-choice-copy');
  info.append(el('strong', '', p.name),el('small', '', p.level),el('p', '', p.description));
  const link = el('a', 'catalog-url', 'Publisher URL'); link.href=p.url; link.target='_blank';link.rel='noopener noreferrer';info.append(link);
  const checkbox = el('input'); checkbox.type='checkbox'; checkbox.checked=selected.has(p.id); checkbox.disabled=busy || state==='external';
  checkbox.setAttribute('aria-label',`Enable ${p.name}`);
  checkbox.onchange=()=>{
    if (p.group==='energized' && checkbox.checked) for (const q of presets.filter(x=>x.group==='energized')) selected.delete(q.id);
    if (checkbox.checked) selected.add(p.id); else selected.delete(p.id);
    render();
  };
  line.append(info,checkbox);
  if (state==='external') line.append(el('small','ux09-foreign','Managed manually in Rules'));
  return line;
}
function render() {
  if (!view) return;
  const groups = [['core','ux09-core'],['comprehensive','ux09-comprehensive'],['energized','ux09-energized']];
  for (const [group,id] of groups) view.querySelector(`#${id}`)?.replaceChildren(...presets.filter(x=>x.group===group).map(makeChoice));
  const changes = dirty();
  const outstanding = [...states.values()].filter(s=>s==='on').length;
  const stamp=lastApplied ? ` · Last validated ${new Date(lastApplied*1000).toLocaleString()}` : '';
  setStatus(changes ? 'Unsaved selection changes' : applied==='PENDING' ? `Saved changes pending hosts update${stamp}` :
    applied==='CURRENT' ? `${outstanding} curated sources configured · Applied${stamp}` : `${outstanding} curated sources configured · Last applied version unknown`);
  const save=view.querySelector('#catalog-save'); if(save)save.disabled=busy||!changes;
  const apply=view.querySelector('#catalog-update');if(apply)apply.disabled=busy;
}
async function refresh() {
  if (!view) return;
  const [s,a] = await Promise.all([call(`${ROOT} status`), call(`${BATCH} applied-status`)]);
  const next=new Map();
  for (const line of s.split('\n')) {
    const [id,status]=line.trim().split('|');
    if (IDS.has(id) && ['on','off','external'].includes(status)) next.set(id,status);
  }
  if (next.size!==presets.length) throw new Error('Catalog and installed presets disagree');
  const marker=a.match(/^BH_UX09_APPLIED=(CURRENT|PENDING|UNKNOWN)$/m)?.[1];
  if (!marker) throw new Error('Unknown applied state');
  states=next;applied=marker;
  const seconds=a.match(/^BH_UX09_LAST_APPLIED_EPOCH=(\d+)$/m)?.[1];
  lastApplied=seconds && Number.isSafeInteger(Number(seconds)) ? Number(seconds) : null;
  original=new Set([...next].filter(([,s])=>s==='on').map(([id])=>id));
  selected=new Set(original);render();
}
async function save() {
  if (!dirty()) return true;
  const values=[...selected].filter(id=>states.get(id)!=='external').sort();
  const csv=values.length?values.join(','):'none';
  if (values.some(id=>!IDS.has(id))) throw new Error('Unexpected preset ID');
  const out=await call(`${BATCH} batch ${csv}`);
  if (!out.includes('BH_UX09_BATCH_APPLIED') && !out.includes('BH_UX09_BATCH_UNCHANGED')) throw new Error('Batch not verified');
  await refresh();return true;
}
async function apply(update) {
  if (busy) return;
  if (!await confirmHostsAction(update ? 'Apply sources & update hosts?' : 'Save source selection?', update ? 'Selected presets will be saved atomically and then hosts will be rebuilt. Manual URLs stay unchanged.' : 'Selected presets will be saved, but active hosts will not change until a later update.')) return;
  busy=true;render();
  try {
    await save();
    if (update) await beginHostsUpdate({confirm:false});
    else showPrompt('Preset selection saved. Update hosts to apply.');
  } catch(err) {showPrompt(`Sources change refused: ${err.message}`,false,6000);}
  finally {busy=false;render();}
}
async function showManual() {
  const list=view?.querySelector('#ux09-manual-list');if(!list)return;
  list.textContent='Loading existing custom subscriptions…';
  try {
    const output=await call(`${BATCH} manual-list`);
    const entries=output.split('\n').filter(Boolean).map(s=>s.match(/^MANUAL\|(on|off)\|(https:\/\/[^\r\n]+|disabled\|https:\/\/[^\r\n]+)$/)).filter(Boolean).slice(0,300);
    if (!entries.length) {list.textContent='No manually added URLs. Use Rules to add one.';return;}
    const nodes=entries.map((match)=>{
      const [raw,state,line]=match;
      const row=el('div','ux09-manual-row');
      const title=el('span','',line.replace(/^disabled\|/,''));
      const action=el('button','ux-secondary-button',state==='on'?'Disable':'Enable');
      action.onclick=async()=>{
        if(busy)return;
        busy=true;action.disabled=true;
        try{await secureToggle('sources',line);await showManual();await refresh();showPrompt('Subscription saved; hosts update required.');}
        catch(err){showPrompt(`Subscription change refused: ${err.message}`,false,5500);}
        finally{busy=false;}
      };
      row.append(title,action);return row;
    });
    list.replaceChildren(...nodes);
  } catch(err){list.textContent=`Cannot load custom subscriptions: ${err.message}`;}
}
function setTab(name) {
  for(const tab of ['presets','mine','advanced']) {
    view.querySelector(`#ux09-${tab}`)?.toggleAttribute('hidden',name!==tab);
    const button=view.querySelector(`#ux09-tab-${tab}`);
    button?.setAttribute('aria-selected',String(name===tab));
  }
  if(name==='mine')void showManual();
}
function mount(section) {
  view=section;
  for(const t of ['presets','mine','advanced'])view.querySelector(`#ux09-tab-${t}`)?.addEventListener('click',()=>setTab(t));
  view.querySelector('#catalog-save').onclick=()=>void apply(false);
  view.querySelector('#catalog-update').onclick=()=>void apply(true);
  view.querySelector('#catalog-view-log').onclick=()=>showHostsOperation();
  view.querySelector('#ux09-open-rules').onclick=()=>router.navigate('hosts');
  view.querySelector('#ux09-open-more').onclick=()=>router.navigate('more');
  document.addEventListener('ux09-hosts-operation-finished',()=>void refresh().catch(()=>{}));
  setTab('presets');
}
function onShow() {if(!view)return;void refresh().catch(err=>{setStatus(`Cannot verify sources: ${err.message}`);showPrompt(err.message,false,4500);});}
function onHide() {}
export {mount,onShow,onHide};
