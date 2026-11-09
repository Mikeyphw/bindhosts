import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from '../../utils/util.js';

const ROOT_CMD = `sh ${moduleDirectory}/bindhosts.sh tracker`;
const PACKAGE_RE = /^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+$/;
let view;
let packages = [];
let selected = '';
let status = null;
let working = false;
let previewLoadedFor = '';

function node(tag, klass, text) {
    const e = document.createElement(tag);
    if (klass) e.className = klass;
    if (text !== undefined) e.textContent = text;
    return e;
}
async function run(cmd) {
    const result = await exec(cmd);
    if (result.errno !== 0) throw new Error((result.stderr || result.stdout || `Command failed: ${result.errno}`).trim());
    return (result.stdout || '').trim();
}
function confirmAction(title, message) {
    return new Promise(resolve => {
        const dialog = view.querySelector('#apps-confirm-dialog');
        const yes = view.querySelector('#apps-confirm');
        const no = view.querySelector('#apps-cancel');
        view.querySelector('#apps-confirm-title').textContent = title;
        view.querySelector('#apps-confirm-body').textContent = message;
        let finished = false;
        const finish = value => {
            if (finished) return;
            finished = true;
            dialog.removeEventListener('closed', closed);
            dialog.removeEventListener('close', closed);
            yes.onclick = null; no.onclick = null;
            dialog.close();
            resolve(value);
        };
        const closed = () => finish(false);
        yes.onclick = () => finish(true);
        no.onclick = () => finish(false);
        dialog.addEventListener('closed', closed);
        dialog.addEventListener('close', closed);
        dialog.show();
    });
}
function displayPackages() {
    const root = view.querySelector('#apps-packages');
    const query = view.querySelector('#apps-search').value.toLowerCase().trim();
    const found = packages.filter(p => p.toLowerCase().includes(query));
    const visible = found.slice(0, 40);
    root.replaceChildren(...visible.map(p => {
        const item = node('button', 'apps-package-button', p);
        item.type = 'button';
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', p === selected ? 'true' : 'false');
        item.onclick = () => selectPackage(p);
        return item;
    }));
    view.querySelector('#apps-load-notice').textContent = `${found.length} matching installed apps${found.length > 40 ? ' (first 40 shown)' : ''}.`;
}
function updateStatusUi() {
    if (!status) return;
    view.querySelector('#apps-monitor-info').textContent = status.monitor_enabled
        ? 'On · checks for installed/updated apps every 120 seconds. Only enrolled apps are blocked automatically.'
        : 'Off · no background package polling.';
    const toggle = view.querySelector('#apps-monitor-toggle');
    toggle.textContent = status.monitor_enabled ? 'Disable monitor' : 'Enable monitor';
    toggle.disabled = working;
    view.querySelector('#apps-auto-count').textContent = String(status.auto_rules);
    view.querySelector('#apps-enrolled-count').textContent = String(status.enrolled.length);
    view.querySelector('#apps-total-count').textContent = String(status.total_rules);
    updateSelectedUi();
}
function updateSelectedUi() {
    const detail = view.querySelector('#apps-detail');
    detail.hidden = !selected;
    if (!selected || !status) return;
    const enrolled = status.enrolled.includes(selected);
    const excluded = status.excluded.includes(selected);
    view.querySelector('#apps-selected-label').textContent = selected;
    view.querySelector('#apps-current-status').textContent = excluded ? 'Excluded from automatic protection' :
        enrolled ? 'Enrolled: receiver trackers are managed automatically' : 'Not enrolled: read-only preview';
    for (const id of ['apps-preview-button', 'apps-enroll-button', 'apps-unenroll-button', 'apps-exclude-button', 'apps-include-button']) {
        view.querySelector(`#${id}`).disabled = working;
    }
    view.querySelector('#apps-enroll-button').hidden = enrolled;
    view.querySelector('#apps-unenroll-button').hidden = !enrolled;
    view.querySelector('#apps-exclude-button').hidden = excluded;
    view.querySelector('#apps-include-button').hidden = !excluded;
}
function selectPackage(pkg) {
    if (!PACKAGE_RE.test(pkg) || !packages.includes(pkg)) return;
    selected = pkg;
    previewLoadedFor = '';
    view.querySelector('#apps-preview').replaceChildren(node('p', 'ux-small', 'Preview this app before enrolling it.'));
    updateSelectedUi();
    displayPackages();
}
async function refreshStatus() {
    const raw = await run(`${ROOT_CMD} json status`);
    const parsed = JSON.parse(raw);
    if (parsed.schema !== 2 || !Array.isArray(parsed.enrolled) || !Array.isArray(parsed.excluded)) {
        throw new Error('TrackerGuard R2 JSON API unavailable');
    }
    status = parsed;
    updateStatusUi();
}
async function refreshInstalledApps() {
    const raw = await run('pm list packages -3');
    const found = raw.split('\n').map(s => s.replace(/^package:/, '').trim()).filter(s => PACKAGE_RE.test(s));
    packages = [...new Set(found)].sort();
    if (!packages.length) throw new Error('No installed user-app packages found');
    displayPackages();
}
async function preview() {
    if (working || !PACKAGE_RE.test(selected)) return;
    const pkg = selected;
    working = true;
    updateSelectedUi();
    try {
        const raw = await run(`${ROOT_CMD} preview ${pkg}`);
        if (selected !== pkg) return;
        const items = raw.split('\n').filter(l => /\|would-block$|\|already-disabled$|\|info-only-provider$|\|unsupported$/.test(l));
        const target = view.querySelector('#apps-preview');
        target.replaceChildren();
        const header = node('p', 'ux-small', `${items.length} matching components. Only receiver components marked would-block are eligible for R2 automation.`);
        target.append(header);
        for (const item of items) {
            const [kind, name, signature, enabled, risk, action] = item.split('|');
            const row = node('div', 'apps-component');
            const label = node('span', '', name);
            const info = node('small', '', `${kind} · ${signature} · ${action}${kind === 'receiver' && action === 'would-block' && risk === 'review' ? ' · Auto eligible' : ''}`);
            row.append(label, info);
            target.append(row);
        }
        previewLoadedFor = pkg;
    } catch (error) {
        previewLoadedFor = '';
        showPrompt(`Preview failed: ${error.message}`, false, 4500);
    } finally {
        working = false;
        updateSelectedUi();
    }
}
async function mutate(action) {
    if (working || !selected || !PACKAGE_RE.test(selected) || !packages.includes(selected)) return;
    const pkg = selected;
    if (action === 'enroll' && previewLoadedFor !== pkg) {
        showPrompt('Preview the package first, then enroll.', false);
        return;
    }
    const messages = {
        enroll: 'Start automatically blocking reviewed, enabled tracker receivers in this app now. App features may change.',
        unenroll: 'Remove R2-owned rules for this app. Existing manual rules will remain.',
        exclude: 'Exclude this app from automatic protection and remove R2-owned rules.',
        include: 'Remove the exclusion. If enrolled, receiver protection will be reapplied.',
    };
    if (!await confirmAction(`${action} ${pkg}?`, messages[action])) return;
    working = true;
    updateSelectedUi();
    try {
        await run(`${ROOT_CMD} ${action} ${pkg}`);
        await refreshStatus();
        showPrompt(`${pkg}: ${action} completed.`);
    } catch (error) {
        showPrompt(`${action} failed: ${error.message}`, false, 4500);
    } finally { working = false; updateSelectedUi(); }
}
async function switchMonitor() {
    if (working || !status) return;
    const action = status.monitor_enabled ? 'disable' : 'enable';
    if (!await confirmAction(`${action} package monitoring?`, action === 'enable'
        ? 'Start root-side polling every 120 seconds. No apps will be automatically enrolled.'
        : 'Stop package polling. Any existing IFW rules will remain in place.')) return;
    working = true;
    updateStatusUi();
    try {
        await run(`${ROOT_CMD} monitor ${action}`);
        await refreshStatus();
        showPrompt(`Monitor ${action}d.`);
    } catch (error) { showPrompt(error.message, false, 4500); }
    finally { working = false; updateStatusUi(); }
}

export function mount(section) {
    view = section;
    view.querySelector('#apps-search').addEventListener('input', displayPackages);
    view.querySelector('#apps-preview-button').onclick = preview;
    view.querySelector('#apps-monitor-toggle').onclick = switchMonitor;
    for (const action of ['enroll','unenroll','exclude','include']) {
        view.querySelector(`#apps-${action}-button`).onclick = () => mutate(action);
    }
}
export function onShow() {
    Promise.all([refreshStatus(), refreshInstalledApps()]).catch(error => {
        if (!view) return;
        view.querySelector('#apps-load-notice').textContent = `Unable to load TrackerGuard: ${error.message}`;
        showPrompt(error.message, false, 4500);
    });
}
export function onHide() {}
