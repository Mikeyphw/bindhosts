// UX09: shared source and Rules-page real progress viewer.
// Commands and displayed lines are fixed/validated; no source URLs or shell interpolation.
import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from './util.js';
const ROOT = `sh ${moduleDirectory}/hosts_operation_ux09.sh`;
const STATUS = new Set(['IDLE', 'RUNNING', 'DONE', 'FAILED', 'INTERRUPTED']);
const STEPS = {
  PREPARING: 'Preparing hosts update',
  DOWNLOADING: 'Downloading sources',
  PARSED: 'Validating downloaded entries',
  SKIPPED_DUPLICATE_URL: 'Skipping repeated source URL',
  DEDUPLICATING: 'Removing duplicate domains',
  ALLOWLIST: 'Applying allowlist exclusions',
  GENERATING: 'Generating hosts file',
  COMMITTING: 'Applying verified hosts file',
  STATS: 'Compiling update statistics',
  UNCHANGED: 'Already up to date',
  DONE: 'Update complete',
  FAILED: 'Update failed'
};
let mounted = false;
let visible = false;
let polling = null;
let currentStatus = 'IDLE';
let lastLineCount = 0;

async function backend(verb) {
  if (!['start', 'status', 'events'].includes(verb)) throw new Error('Unknown operation');
  const r = await exec(`${ROOT} ${verb}`);
  if (r?.errno !== 0) throw new Error(`Hosts operation ${verb} refused (exit ${r?.errno ?? '?'})`);
  return String(r.stdout ?? '');
}
function byId(id) { return document.getElementById(id); }
function lines(input) {
  return input.split(/\r?\n/).filter(Boolean).slice(-150).filter(v =>
    /^[A-Z_]+\|[A-Za-z0-9_ .=:\-|]+$/.test(v) && v.length < 180);
}
function renderEvents(rows) {
  const display = byId('ux09-operation-lines');
  if (!display) return;
  const formatted = rows.map(row => {
    const [tag, ...rest] = row.split('|');
    return `[${tag}] ${rest.join(' · ')}`;
  });
  display.textContent = formatted.join('\n') || 'Waiting for backend progress events…';
  if (rows.length !== lastLineCount && visible) display.scrollTop = display.scrollHeight;
  lastLineCount = rows.length;
  const statsRow = [...rows].reverse().find(line => line.startsWith('STATS|'));
  const summary = byId('ux09-operation-summary');
  if (summary && statsRow) {
    const parts = statsRow.split('|').slice(1);
    if (parts.length === 8 && parts.every(v => /^\d+$/.test(v))) {
      const [raw, dup, unique, excluded, final, sources, skipped, changed] = parts.map(Number);
      summary.textContent = `${raw.toLocaleString()} raw entries · ${dup.toLocaleString()} duplicates removed · ${unique.toLocaleString()} unique · ${excluded.toLocaleString()} allowlisted · ${final.toLocaleString()} final · ${sources} downloads · ${skipped} repeated URLs skipped · ${changed ? 'Hosts changed' : 'Already current'}`;
    }
  }
}
let reading = false;
async function poll() {
  if (reading) return;
  reading = true;
  try {
    const output = await backend('status');
    const state = output.match(/^BH_UX09_STATE=(IDLE|RUNNING|DONE|FAILED|INTERRUPTED)$/m)?.[1];
    if (!STATUS.has(state)) throw new Error('Unrecognized operation state');
    const step = output.match(/^BH_UX09_STEP=([A-Z_]+)$/m)?.[1];
    const previousStatus = currentStatus;
    currentStatus = state;
    const label = byId('ux09-operation-stage');
    const status = byId('ux09-operation-status');
    if (label) label.textContent = state === 'RUNNING' ? STEPS[step] || 'Updating hosts…' :
      state === 'DONE' ? 'Update finished and backend confirmed success' :
      state === 'FAILED' ? 'Update failed — review log and active hosts' :
      state === 'INTERRUPTED' ? 'Update interrupted — inspect before retrying' : 'No update started';
    if (status) { status.textContent = state; status.dataset.state = state; }
    renderEvents(lines(await backend('events')));
    document.querySelectorAll('[data-ux09-running]').forEach(el => {
      el.textContent = state === 'RUNNING' ? 'Updating hosts…' : '';
    });
    if (state !== 'RUNNING' && polling) {
      clearInterval(polling); polling = null;
      if (state === 'DONE' && previousStatus === 'RUNNING') showPrompt('Hosts update verified. View the update summary.');
      if (state === 'FAILED' && previousStatus === 'RUNNING') showPrompt('Update failed. Previous hosts may be retained; verify status.', false, 6000);
      document.dispatchEvent(new CustomEvent('ux09-hosts-operation-finished', { detail: { state } }));
    }
  } catch (err) {
    const s = byId('ux09-operation-stage'); if (s) s.textContent = `Cannot verify update: ${err.message}`;
    if (polling) { clearInterval(polling); polling = null; }
  } finally { reading = false; }
}
function watch() {
  if (!polling) polling = setInterval(() => { void poll(); }, 1050);
  void poll();
}
export function showHostsOperation() {
  const panel = byId('ux09-operation-overlay');
  if (!panel) return;
  panel.hidden = false; visible = true;
  watch();
}
let asking = false;
export function confirmHostsAction(title, description) {
  if (asking) return Promise.resolve(false);
  const dialog=byId('ux09-operation-confirm');
  const heading=byId('ux09-operation-confirm-title');
  const content=byId('ux09-operation-confirm-message');
  const yes=byId('ux09-operation-confirm-yes');
  const no=byId('ux09-operation-confirm-no');
  if (!dialog || !heading || !content || !yes || !no) return Promise.resolve(false);
  asking=true; heading.textContent=title; content.textContent=description;
  return new Promise(resolve=>{
    let done=false;
    const finish=(value)=>{
      if(done)return;done=true;asking=false;
      yes.removeEventListener('click',accept);no.removeEventListener('click',reject);
      dialog.removeEventListener('closed',reject);dialog.removeEventListener('close',reject);
      dialog.close();resolve(value);
    };
    const accept=()=>finish(true),reject=()=>finish(false);
    yes.addEventListener('click',accept);no.addEventListener('click',reject);
    dialog.addEventListener('closed',reject);dialog.addEventListener('close',reject);
    dialog.show();
  });
}
export async function beginHostsUpdate({confirm = true} = {}) {
  const panel = byId('ux09-operation-overlay');
  if (!panel) throw new Error('Operation viewer unavailable');
  const s = await backend('status');
  const state = s.match(/^BH_UX09_STATE=(IDLE|RUNNING|DONE|FAILED|INTERRUPTED)$/m)?.[1];
  if (state === 'RUNNING') { showHostsOperation(); return; }
  if (state === 'INTERRUPTED') {
    showHostsOperation(); throw new Error('Previous update interrupted; inspect the operation before restarting');
  }
  if (confirm && !await confirmHostsAction('Update hosts?', 'Enabled sources will be downloaded and validated. Existing hosts stay in place until a verified commit.')) return;
  byId('ux09-operation-summary').textContent = '';
  lastLineCount = 0;
  const output = await backend('start');
  if (!/^BH_UX09_STARTED=\d+$/m.test(output)) throw new Error('Update launch was not acknowledged');
  showHostsOperation();
}
export function mountHostsOperationUI() {
  if (mounted) return;
  const overlay = byId('ux09-operation-overlay');
  if (!overlay) return;
  mounted = true;
  byId('ux09-operation-close')?.addEventListener('click', () => {
    overlay.hidden = true; visible = false; // NEVER cancel the worker
  });
  byId('ux09-operation-refresh')?.addEventListener('click', () => { void poll(); });
  // Read-only restoration after a WebUI reopen. Show the panel only on user action.
  void backend('status').then(output => {
    const state = output.match(/^BH_UX09_STATE=([A-Z]+)$/m)?.[1];
    if (state === 'RUNNING') watch();
  }).catch(() => {});
}
