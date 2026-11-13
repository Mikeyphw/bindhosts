// UX08: explicit hosts controls. Never infer success from an icon tap or stdout alone.
import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from './util.js';

const VALID = new Set(['ACTIVE', 'PAUSED', 'INACTIVE', 'DISABLED']);
const WAITING = 'Checking blocking status…';
let busy = false;
let latest = null;
let token = 0;

function elements() {
    return {
        state: document.getElementById('hosts-control-status'),
        detail: document.getElementById('hosts-control-detail'),
        toggle: document.getElementById('hosts-control-toggle'),
        toggleLabel: document.getElementById('hosts-control-toggle-label'),
        update: document.getElementById('hosts-control-update'),
        refresh: document.getElementById('hosts-control-refresh'),
        toggleIcon: document.getElementById('hosts-control-toggle-icon'),
    };
}

async function command(action) {
    const result = await exec(`sh ${moduleDirectory}/bindhosts.sh --hosts-control ${action}`);
    if (result?.errno !== 0) {
        // Don't display arbitrary backend output as a success or raw HTML.
        throw new Error(`Backend refused ${action} (exit ${result?.errno ?? 'unknown'})`);
    }
    return String(result?.stdout ?? '');
}

function applyState(state, message = '') {
    const el = elements();
    if (!el.state || !el.toggle || !el.update) return;
    const names = {
        ACTIVE: ['Configured active', 'Generated hosts rules are present. DNS enforcement is not independently verified.'],
        PAUSED: ['Paused', 'The previous hosts file is saved for a reversible resume.'],
        INACTIVE: ['Not configured', 'Run Update hosts to generate the blocking list.'],
        DISABLED: ['Module disabled', 'Enable the KernelSU module before changing hosts blocking.'],
        UNKNOWN: ['Status unavailable', 'No changes were made. Check module access and diagnostics.'],
    };
    const current = names[state] || names.UNKNOWN;
    el.state.textContent = busy ? 'Working…' : current[0];
    el.detail.textContent = message || current[1];
    el.state.dataset.state = state;
    el.toggleLabel.textContent = state === 'PAUSED' ? 'Resume blocking' : 'Pause blocking';
    el.toggle.setAttribute('aria-label', el.toggleLabel.textContent);
    const glyph = el.toggleIcon?.querySelector('path');
    if (glyph) glyph.setAttribute('d', state === 'PAUSED'
        ? 'M320-200v-560l440 280-440 280Z'
        : 'M240-760h160v560H240zm320 0h160v560H560z');
    el.toggle.classList.toggle('hosts-control-resume', state === 'PAUSED');
    el.toggle.disabled = busy || !['ACTIVE', 'PAUSED'].includes(state);
    el.update.disabled = busy || !['ACTIVE', 'INACTIVE'].includes(state);
    if (el.refresh) el.refresh.disabled = busy;
}

export async function refreshHostsControls() {
    if (busy) return;
    const mine = ++token;
    applyState(latest ?? 'UNKNOWN', WAITING);
    try {
        const output = await command('status');
        const match = output.match(/^BH_HOSTS_STATE=(ACTIVE|PAUSED|INACTIVE|DISABLED)$/m);
        if (!match || !VALID.has(match[1])) throw new Error('Unrecognized backend status');
        if (mine !== token) return;
        latest = match[1];
        applyState(latest);
    } catch (error) {
        if (mine !== token) return;
        latest = 'UNKNOWN';
        applyState('UNKNOWN', error.message);
    }
}

async function perform(action) {
    if (busy) return;
    ++token;
    busy = true;
    const initial = latest;
    applyState(initial || 'UNKNOWN', 'Applying requested change…');
    try {
        const before = await command('status');
        const oldState = before.match(/^BH_HOSTS_STATE=(ACTIVE|PAUSED|INACTIVE|DISABLED)$/m)?.[1];
        const expectedBefore = action === 'pause' ? 'ACTIVE' : action === 'resume' ? 'PAUSED' : null;
        if (!oldState || (expectedBefore && oldState !== expectedBefore) || (action === 'update' && !['ACTIVE', 'INACTIVE'].includes(oldState))) {
            throw new Error('Blocking state changed; refresh before retrying');
        }
        const output = await command(action);
        const marker = `BH_HOSTS_${action.toUpperCase()}_PASS`;
        if (!output.split(/\r?\n/).includes(marker)) throw new Error('Backend returned no verified success marker');
        const after = await command('status');
        const confirmed = after.match(/^BH_HOSTS_STATE=(ACTIVE|PAUSED|INACTIVE|DISABLED)$/m)?.[1];
        const expected = action === 'pause' ? 'PAUSED' : 'ACTIVE';
        if (confirmed !== expected) throw new Error('Read-back did not confirm the requested state');
        latest = confirmed;
        showPrompt(action === 'pause' ? 'Hosts blocking paused.' : action === 'resume' ? 'Hosts blocking resumed.' : 'Hosts update completed.');
    } catch (error) {
        latest = 'UNKNOWN';
        showPrompt(`Hosts action not verified: ${error.message}`, false);
    } finally {
        busy = false;
        applyState(latest || 'UNKNOWN');
        // Re-read after failures to avoid leaving a stale control state.
        if (latest === 'UNKNOWN') void refreshHostsControls();
    }
}

export function mountHostsControls() {
    const el = elements();
    if (!el.toggle || !el.update || !el.refresh) return;
    el.toggle.addEventListener('click', () => perform(latest === 'PAUSED' ? 'resume' : 'pause'));
    el.update.addEventListener('click', () => perform('update'));
    el.refresh.addEventListener('click', () => refreshHostsControls());
    applyState('UNKNOWN');
}
