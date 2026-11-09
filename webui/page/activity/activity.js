import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from '../../utils/util.js';
import { router } from '../../route.js';

const API = `sh ${moduleDirectory}/ux05_diagnostics.sh`;
const help = Object.freeze({
  HOSTS_UPDATE_FAILED: 'Hosts update failed. Check enabled HTTPS sources and retry from Sources.',
  HOSTS_UPDATE_OK: 'Hosts sources validated and committed.',
  HOSTS_ATOMIC_COMMIT: 'Hosts file committed using atomic replacement.',
  HOSTS_INPLACE_COMMIT: 'Hosts verified after an in-place fallback. This path is not power-loss atomic.',
  HOSTS_RESET_FAILED: 'Reset was refused. Inspect recovery status before retrying.',
  HOSTS_TOGGLE_FAILED: 'Hosts toggle failed. Existing data should remain preserved.',
  HOSTS_ALLOWLIST_FAILED: 'Immediate allowlisting failed; check the domain and state journal.',
  HOSTS_RESET_OK: 'Hosts reset completed.',
  HOSTS_TOGGLE_OK: 'Hosts protection toggled.',
  HOSTS_ALLOWLIST_OK: 'Immediate allowlisting completed.',
  RECOVERY_APPLIED: 'Pending journal restored to its pre-operation bytes.',
  RECOVERY_WRITE_FAILED: 'Recovery failed. Preserve the journal; avoid hosts updates until repaired.',
  RECOVERY_ALREADY_DONE: 'The target matched the saved preimage; stale journal was cleaned.',
  RESPONSE_SET_OK: 'Blocked-image setting updated.',
  RESPONSE_SET_FAILED: 'HTTP responder setting failed. Check the local port and server status.',
  RESPONSE_START_FAILED: 'Boot-time responder startup failed; check that normal blocking was restored.',
  RESPONSE_STARTED: 'Optional HTTP responder started.',
  TG_ACTION_OK: 'TrackerGuard action completed. Manual IFW rules remain separately owned.',
  TG_ACTION_FAILED: 'TrackerGuard action failed. Check the affected app before retrying.',
  NONE: 'No recorded failure.'
});
let view = null;
let records = [];
let busy = false;
async function call(verb, argument = '') {
  if (!['status','history','export'].includes(verb)) throw new Error('Unsupported diagnostic operation');
  if (argument && !/^(?:[1-9]|[1-9][0-9]|100)$/.test(argument)) throw new Error('Invalid history limit');
  const result = await exec(`${API} ${verb}${argument ? ` ${argument}` : ''}`);
  if (result.errno !== 0) throw new Error((result.stderr || result.stdout || 'Diagnostics unavailable').trim());
  return (result.stdout || '').trim();
}
function element(tag, klass, value) {
  const node = document.createElement(tag);
  if (klass) node.className = klass;
  if (value !== undefined) node.textContent = value;
  return node;
}
function dateLabel(timestamp) {
  const date = new Date(timestamp * 1000);
  return Number.isFinite(date.getTime()) ? date.toLocaleString() : 'Unknown time';
}
function renderHistory() {
  if (!view) return;
  const filter = view.querySelector('#ux05-result-filter').value;
  const list = view.querySelector('#ux05-event-list');
  const selected = [...records].reverse().filter(r => filter === 'all' || r.result === filter);
  list.replaceChildren();
  if (!selected.length) {
    list.append(element('p', 'ux05-note', 'No recorded events match this filter.'));
    return;
  }
  for (const event of selected) {
    const row = element('article', 'ux05-event');
    row.dataset.result = event.result;
    const heading = element('div', 'ux05-event-heading');
    heading.append(element('span', 'ux05-event-title', `${event.area} · ${event.action} · ${event.result}`),
      element('time', 'ux05-event-time', dateLabel(event.ts)));
    const detail = element('p', 'ux05-event-detail', help[event.code] || 'Operation recorded. Review status and retry only if needed.');
    const code = element('small', 'ux05-event-code', event.code);
    row.append(heading, detail, code);
    list.append(row);
  }
}
async function refresh() {
  if (!view || busy) return;
  busy = true;
  view.querySelector('#ux05-refresh').disabled = true;
  try {
    const [rawStatus, rawHistory] = await Promise.all([call('status'),call('history','100')]);
    const status = JSON.parse(rawStatus);
    const history = JSON.parse(rawHistory);
    if (status.schema !== 1 || !Array.isArray(history)) throw new Error('Unsupported diagnostics schema');
    records = history.filter(r => Number.isSafeInteger(r.ts) &&
      /^[a-z]+$/.test(r.area) && /^[a-z]+$/.test(r.action) &&
      ['ok','fail','warning','info'].includes(r.result) && /^[A-Z0-9_]{1,48}$/.test(r.code));
    view.querySelector('#ux05-events').textContent = String(status.receipts);
    view.querySelector('#ux05-fails').textContent = String(status.failures);
    view.querySelector('#ux05-sources').textContent = String(status.enabled_sources);
    view.querySelector('#ux05-health').textContent =
      `Recovery journal: ${status.journal} · HTTP image: ${status.response_mode} · Tracker monitor: ${status.monitor_enabled ? 'on' : 'off'}`;
    view.querySelector('#ux05-last-ok').textContent =
      `${status.last_ok_ts ? `Last success: ${dateLabel(status.last_ok_ts)}` : 'No recorded success yet.'} ` +
      `${status.last_failure_code !== 'NONE' ? `Last failure: ${status.last_failure_code}` : ''}`;
    renderHistory();
  } catch (error) {
    view.querySelector('#ux05-health').textContent = `Unable to load diagnostics: ${error.message}`;
    showPrompt(error.message, false, 5000);
  } finally {
    busy = false;
    view.querySelector('#ux05-refresh').disabled = false;
  }
}
function confirmExport() {
  return new Promise(resolve => {
    const dialog = view.querySelector('#ux05-export-confirm');
    const accept = view.querySelector('#ux05-export-ok');
    const cancel = view.querySelector('#ux05-export-cancel');
    let decided = false;
    const done = value => {
      if (decided) return;
      decided = true;
      dialog.removeEventListener('closed', closed);
      accept.onclick = null;
      cancel.onclick = null;
      dialog.close();
      resolve(value);
    };
    const closed = () => done(false);
    dialog.addEventListener('closed', closed);
    accept.onclick = () => done(true);
    cancel.onclick = () => done(false);
    dialog.show();
  });
}
async function exportDiagnostics() {
  if (busy || !await confirmExport()) return;
  busy = true;
  view.querySelector('#ux05-export').disabled = true;
  try {
    const output = await call('export');
    const match = output.match(/^BH_UX05_EXPORT_PATH=(\/storage\/emulated\/0\/Download\/bindhosts_diagnostics_[A-Za-z0-9_]+\.json)$/);
    if (!match) throw new Error('Unexpected export receipt');
    view.querySelector('#ux05-export-result').textContent = `Saved: ${match[1]}`;
    showPrompt('Redacted diagnostic report saved to Downloads.');
  } catch (error) {
    showPrompt(`Diagnostic export failed: ${error.message}`, false, 5000);
  } finally {
    busy = false;
    view.querySelector('#ux05-export').disabled = false;
  }
}
export function mount(section) {
  view = section;
  view.querySelector('#ux05-back').onclick = () => router.navigate('more');
  view.querySelector('#ux05-refresh').onclick = refresh;
  view.querySelector('#ux05-result-filter').onchange = renderHistory;
  view.querySelector('#ux05-export').onclick = exportDiagnostics;
}
export function onShow() { refresh(); }
export function onHide() {}
