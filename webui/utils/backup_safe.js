// UX06: fixed-verb backup API. Never pass selected file contents/paths into shell code.
import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from './util.js';

const backend = `sh ${moduleDirectory}/config_backup_safe.sh`;
const snapshotRE = /^bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$/;
const filenameRE = /^bindhosts-backup-(bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6})\.tar$/;
let busy = false;
let root;

async function call(verb, parameter = '') {
    const allowed = new Set(['status','health','list','create','verify','preview','restore','export','import','imports']);
    if (!allowed.has(verb)) throw new Error('Unknown backup action');
    if (parameter && !snapshotRE.test(parameter) && !filenameRE.test(parameter)) {
        throw new Error('Invalid backup identifier');
    }
    const result = await exec(`${backend} ${verb}${parameter ? ` ${parameter}` : ''}`);
    if (result.errno !== 0) throw new Error((result.stderr || result.stdout || 'Backup command failed').trim());
    return (result.stdout || '').trim();
}
function show(id, value) { root.querySelector(`#${id}`).textContent = value; }
function selected() {
    const id = root.querySelector('#ux06-select').value;
    if (!snapshotRE.test(id)) throw new Error('Select a valid backup first');
    return id;
}
function confirmAction(title, body) {
    return new Promise(resolve => {
        const dialog = root.querySelector('#ux06-confirm-dialog');
        const yes = root.querySelector('#ux06-confirm-yes');
        const no = root.querySelector('#ux06-confirm-no');
        root.querySelector('#ux06-confirm-title').textContent = title;
        root.querySelector('#ux06-confirm-body').textContent = body;
        let finished = false;
        const done = ok => {
            if (finished) return;
            finished = true;
            yes.onclick = null;
            no.onclick = null;
            dialog.removeEventListener('closed', closed);
            dialog.removeEventListener('close', closed);
            dialog.close();
            resolve(ok);
        };
        const closed = () => done(false);
        dialog.addEventListener('closed', closed);
        dialog.addEventListener('close', closed);
        yes.onclick = () => done(true);
        no.onclick = () => done(false);
        dialog.show();
    });
}
async function refresh() {
    const [status, health, list, imports] = await Promise.all([call('status'),call('health'),call('list'),call('imports')]);
    show('ux06-status', status);
    show('ux06-health', health);
    const select = root.querySelector('#ux06-select');
    const previous = select.value;
    const items = list.split('\n').filter(line => line && line !== 'BH_BACKUP_LIST_EMPTY').map(line => {
        const [id, size] = line.split('|');
        if (!snapshotRE.test(id) || !/^[0-9]+$/.test(size)) throw new Error('Invalid backup listing');
        return {id, size: Number(size)};
    });
    select.replaceChildren();
    for (const item of items.reverse()) {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = `${item.id} · ${item.size} bytes`;
        select.append(option);
    }
    if (items.some(item => item.id === previous)) select.value = previous;
    show('ux06-count', `${items.length} private backups`);
    const imported = root.querySelector('#ux06-import-select');
    imported.replaceChildren();
    const available = imports.split('\n').filter(line => line && line !== 'BH_BACKUP_IMPORTS_EMPTY');
    for (const name of available) {
        if (!filenameRE.test(name)) throw new Error('Unexpected available archive name');
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        imported.append(option);
    }
    root.querySelector('#ux06-import').disabled = !available.length;
    for (const name of ['verify','preview','restore','export']) root.querySelector(`#ux06-${name}`).disabled = !items.length;
}
async function perform(kind) {
    if (busy) return;
    let id = '';
    let importName = '';
    try {
        if (['verify','preview','restore','export'].includes(kind)) id = selected();
        if (kind === 'import') {
            importName = root.querySelector('#ux06-import-select').value;
            if (!filenameRE.test(importName)) throw new Error('Select a trusted archive from Downloads');
        }
        if (kind === 'restore') {
            const differences = await call('preview', id);
            show('ux06-progress', differences);
            if (!await confirmAction('Restore configuration?',
                `${differences}\n\nThe selected backup will replace five configuration files. Active hosts are not rebuilt automatically. Run Update hosts afterward.`)) return;
        }
        if (kind === 'export' && !await confirmAction('Export sensitive configuration?',
            'The exported archive includes your source URLs, allowed/blocked domains and custom mappings. Anyone with access to Downloads may read it.')) return;
        if (kind === 'verify') {
            const result = await call('preview', id);
            show('ux06-progress', result);
            showPrompt('Backup verified; preview available below.');
            return;
        }
        busy = true;
        for (const el of root.querySelectorAll('.ux06-panel button')) el.disabled = true;
        show('ux06-progress', `Running ${kind}…`);
        const result = await call(kind, kind === 'import' ? importName : id);
        show('ux06-progress', result);
        showPrompt(kind === 'restore' ? 'Configuration restored. Update hosts to apply it.' : result);
        await refresh();
    } catch (error) {
        show('ux06-progress', error.message);
        showPrompt(error.message, false, 5000);
    } finally {
        busy = false;
        root.querySelectorAll('.ux06-panel button').forEach(b => { b.disabled = false; });
        root.querySelector('#ux06-refresh').disabled = false;
        const has = Boolean(root.querySelector('#ux06-select').options.length);
        root.querySelector('#ux06-import').disabled = !root.querySelector('#ux06-import-select').options.length;
        for (const name of ['verify','preview','restore','export']) root.querySelector(`#ux06-${name}`).disabled = !has;
    }
}
export function mountBackupControls(section) {
    root = section;
    for (const action of ['create','verify','preview','restore','export','import','imports']) {
        root.querySelector(`#ux06-${action}`).onclick = () => perform(action);
    }
    root.querySelector('#ux06-refresh').onclick = () => refresh().catch(error => show('ux06-progress',error.message));
}
export function refreshBackupControls() {
    if (!root) return;
    refresh().catch(error => { show('ux06-progress', error.message); showPrompt(error.message,false,5000); });
}
