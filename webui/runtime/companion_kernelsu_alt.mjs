/** P05 Android-only UX10 shell adapter: finite hosts operations + read-only UI projection.
 * Other UX10 commands still fail closed and the KernelSU WebUI build is untouched.
 */
import { nativeAppTransport } from './companion_transport.mjs';
const MOD = '/data/adb/modules/bindhosts';
const HOSTS_READ = `sh ${MOD}/bindhosts.sh --hosts-control status`;
const MODULE_PROP_READ = `cat "${MOD}/module.prop"`;
const PAUSE = `sh ${MOD}/bindhosts.sh --hosts-control pause`;
const RESUME = `sh ${MOD}/bindhosts.sh --hosts-control resume`;
const UPDATE_START = `sh ${MOD}/hosts_operation_ux09.sh start`;
const UPDATE_STATUS = `sh ${MOD}/hosts_operation_ux09.sh status`;
const UPDATE_EVENTS = `sh ${MOD}/hosts_operation_ux09.sh events`;
let transport = null;
const success = stdout => Object.freeze({ errno: 0, stdout, stderr: '' });
const refused = () => Object.freeze({ errno: 13, stdout: '', stderr: 'BH_APP01_P05_REFUSED: unqualified command' });
function native() {
  if (!transport) {
    if (!window.BindhostsBridge || typeof window.BindhostsBridge.postMessage !== 'function') throw new Error('Native bridge unavailable');
    transport = nativeAppTransport(window.BindhostsBridge);
  }
  return transport;
}
function eventsText(encoded) {
  const binary = atob(encoded);
  // UX09 checks its own event format and length; discard anything unexpected.
  const text = new TextDecoder('utf-8', {fatal:true}).decode(Uint8Array.from(binary, c => c.charCodeAt(0)));
  if (text.length > 4600 || text.split('\n').some(row => row && (row.length >= 180 || !/^[A-Z_]+\|[A-Za-z0-9_ .=:\-|]+$/.test(row)))) throw new Error('Invalid events');
  return text;
}
export async function exec(command) {
  if (typeof command !== 'string') return refused();
  try {
    if (command === HOSTS_READ) {
      const state = await native().invoke('status');
      return success(`BH_HOSTS_STATE=${state.hosts}\n`);
    }
    if (command === MODULE_PROP_READ) {
      const hello = await native().invoke('hello');
      const state = await native().invoke('status');
      return success(`id=bindhosts\nversion=module versionCode ${hello.versionCode}\ndescription=status: ${state.hosts.toLowerCase()} (module read-back, not DNS proof)\n`);
    }
    if (command === PAUSE || command === RESUME) {
      const verb = command === PAUSE ? 'pause' : 'resume';
      const result = await native().invoke(verb);
      return success(`BH_HOSTS_${verb.toUpperCase()}_PASS\nBH_HOSTS_STATE=${result.hosts}\n`);
    }
    if (command === UPDATE_START) {
      // UX09's UI expects a numeric receipt. Native control already confirmed
      // journaled launch; a fixed numeric sentinel is not a process ID.
      await native().invoke('update-start');
      return success('BH_UX09_STARTED=1\n');
    }
    if (command === UPDATE_STATUS) {
      const result = await native().invoke('update-status');
      return success(`BH_UX09_STATE=${result.operation}\n${result.step !== 'NONE' ? `BH_UX09_STEP=${result.step}\n` : ''}${result.receipt !== 'NONE' ? `BH_UX09_RECEIPT=${result.receipt}\n` : ''}`);
    }
    if (command === UPDATE_EVENTS) {
      const result = await native().invoke('update-events');
      return success(eventsText(result.encoded));
    }
  } catch { return refused(); }
  return refused();
}
export function toast(message) {
  if (typeof message === 'string' && message.length <= 160) console.info('Bindhosts companion: ' + message);
}
export function spawn() { throw new Error('BH_APP01_P05_REFUSED: arbitrary streaming commands disabled'); }
export const P04_COMMANDS = Object.freeze([HOSTS_READ, MODULE_PROP_READ]);
export const P05_COMMANDS = Object.freeze([PAUSE, RESUME, UPDATE_START, UPDATE_STATUS, UPDATE_EVENTS]);
