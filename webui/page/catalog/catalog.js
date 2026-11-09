import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from '../../utils/util.js';
import presets from '../../catalog-presets.json';

let view;
let states = new Map();
let busy = false;
const commandRoot = `sh ${moduleDirectory}/source_catalog.sh`;
const PRESET_IDS = new Set(presets.map(p => p.id));

function el(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined) result.textContent = text;
    return result;
}

async function run(command) {
    const result = await exec(command);
    if (result.errno !== 0) throw new Error((result.stderr || result.stdout || 'Command failed').trim());
    return result.stdout.trim();
}

function confirmAction(title, description) {
    return new Promise(resolve => {
        const dialog = view.querySelector('#catalog-confirm-dialog');
        const ok = view.querySelector('#catalog-confirm');
        const cancel = view.querySelector('#catalog-cancel');
        view.querySelector('#catalog-confirm-title').textContent = title;
        view.querySelector('#catalog-confirm-body').textContent = description;
        let answered = false;
        const finish = value => {
            if (answered) return;
            answered = true;
            dialog.removeEventListener('closed', closed);
            dialog.removeEventListener('close', closed);
            ok.onclick = null;
            cancel.onclick = null;
            dialog.close();
            resolve(value);
        };
        const closed = () => finish(false);
        ok.onclick = () => finish(true);
        cancel.onclick = () => finish(false);
        dialog.addEventListener('closed', closed);
        dialog.addEventListener('close', closed);
        dialog.show();
    });
}

function card(preset) {
    const state = states.get(preset.id) || 'off';
    const item = el('article', 'ux-card catalog-card');
    const upper = el('div', 'catalog-card-top');
    const title = el('div');
    title.append(el('h2', '', preset.name), el('p', 'ux-small', preset.level));
    const badge = el('span', `ux-state ${state === 'on' ? 'ux-on' : ''}`, {
        on: 'Enabled', off: 'Not selected', external: 'Custom entry'
    }[state] || 'Unknown');
    upper.append(title, badge);
    const desc = el('p', 'catalog-description', preset.description);
    const link = el('a', 'catalog-url', preset.url);
    link.href = preset.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    const footer = el('div', 'catalog-card-footer');
    const action = el('button', 'ux-secondary-button', state === 'on' ? 'Disable' : 'Enable');
    action.type = 'button';
    if (state === 'external') {
        action.textContent = 'Managed manually';
        action.disabled = true;
        action.title = 'Existing source is user-owned; open Rules to edit it';
    } else {
        action.disabled = busy;
        action.onclick = () => changePreset(preset, state === 'on' ? 'disable' : 'enable');
    }
    footer.append(action);
    item.append(upper, desc, link, footer);
    return item;
}

function render() {
    if (!view) return;
    const list = view.querySelector('#catalog-list');
    list.replaceChildren(...presets.map(card));
    view.querySelector('#catalog-update').disabled = busy;
}

async function refresh() {
    const output = await run(`${commandRoot} status`);
    const next = new Map();
    for (const line of output.split('\n')) {
        const [id, status] = line.trim().split('|');
        if (PRESET_IDS.has(id) && ['on', 'off', 'external'].includes(status)) next.set(id, status);
    }
    if (next.size !== presets.length) throw new Error('Catalog status does not match installed preset data.');
    states = next;
    const configured = [...states.values()].filter(s => s !== 'off').length;
    view.querySelector('#catalog-status').textContent = `${configured} of ${presets.length} catalog sources configured. Update hosts to apply any changes.`;
    render();
}

async function changePreset(preset, action) {
    if (busy || !PRESET_IDS.has(preset.id)) return;
    const yes = await confirmAction(`${action === 'enable' ? 'Enable' : 'Disable'} ${preset.name}?`,
        action === 'enable'
          ? `${preset.name} will be added to your sources. Existing custom sources remain unchanged. Selecting an Energized tier replaces other catalog-managed Energized tiers.`
          : `${preset.name} will be disabled in your catalog settings. Custom entries will not be deleted.`);
    if (!yes) return;
    busy = true;
    render();
    try {
        await run(`${commandRoot} ${action} ${preset.id}`);
        await refresh();
        showPrompt(`${preset.name}: settings saved. Update hosts to apply.`);
    } catch (error) {
        showPrompt(error.message, false, 4500);
    } finally {
        busy = false;
        render();
    }
}

async function updateHosts() {
    if (busy) return;
    if (!await confirmAction('Update hosts now?',
        'Download enabled sources and rebuild hosts protection. The existing updater does not yet guarantee atomic rollback; review the result and use a backup if needed.')) return;
    busy = true;
    render();
    view.querySelector('#catalog-status').textContent = 'Updating hosts…';
    try {
        const result = await run(`sh ${moduleDirectory}/bindhosts.sh --force-update`);
        showPrompt(result.includes('failed') ? 'Update finished; check details in the activity log.' : 'Hosts update finished.');
    } catch (error) {
        showPrompt(`Hosts update failed: ${error.message}`, false, 4500);
    } finally {
        busy = false;
        try { await refresh(); } catch (error) { view.querySelector('#catalog-status').textContent = error.message; }
        render();
    }
}

export function mount(section) {
    view = section;
    view.querySelector('#catalog-update').addEventListener('click', updateHosts);
}

export function onShow() {
    if (!view) return;
    refresh().catch(err => {
        view.querySelector('#catalog-status').textContent = `Cannot load catalog: ${err.message}`;
        showPrompt(err.message, false, 4500);
    });
}
export function onHide() {}
