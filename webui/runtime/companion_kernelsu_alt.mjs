/**
 * P04 adapter used ONLY by the standalone Android build of the existing UX10 UI.
 * A closed command registry maps two READS into the typed native bridge. Everything
 * else, including shell operators, spawn, hosts writes, IFW and reboot, is refused.
 * This module MUST NOT be imported by the ordinary KernelSU/WebUI-X bundle.
 */
import { nativeAppTransport } from './companion_transport.mjs';

const HOSTS_READ = 'sh /data/adb/modules/bindhosts/bindhosts.sh --hosts-control status';
const MODULE_PROP_READ = 'cat "/data/adb/modules/bindhosts/module.prop"';
let transport = null;

const success = stdout => Object.freeze({ errno: 0, stdout, stderr: '' });
const refused = () => Object.freeze({ errno: 13, stdout: '', stderr: 'BH_APP01_P04_READ_ONLY: operation unavailable in companion preview' });

function native() {
  if (!transport) {
    if (!window.BindhostsBridge || typeof window.BindhostsBridge.postMessage !== 'function') {
      throw new Error('Trusted native bridge unavailable');
    }
    transport = nativeAppTransport(window.BindhostsBridge);
  }
  return transport;
}

export async function exec(command) {
  // Exact equality, not substring, wildcard or user-controlled prefix matching.
  // No parameters from a UX10 input field reach the native root executor.
  if (typeof command !== 'string') return refused();
  try {
    if (command === HOSTS_READ) {
      const status = await native().invoke('status');
      return success(`BH_HOSTS_STATE=${status.hosts}\n`);
    }
    if (command === MODULE_PROP_READ) {
      const hello = await native().invoke('hello');
      const status = await native().invoke('status');
      // This is an explicitly synthetic *display-only* projection, not a
      // claimed full module.prop or a substitute for its actual file contents.
      return success(`id=bindhosts\nversion=module versionCode ${hello.versionCode}\ndescription=status: ${status.hosts.toLowerCase()} (module read-back, not DNS proof)\n`);
    }
  } catch {
    // Do not expose native/root errors to the WebUI or pretend success.
    return refused();
  }
  return refused();
}

export function toast(message) {
  // No Android toast/system access. A rejected operation is not an approval.
  if (typeof message === 'string' && message.length <= 160) console.info('Bindhosts companion: ' + message);
}

export function spawn() {
  throw new Error('BH_APP01_P04_READ_ONLY: streaming/mutating commands disabled');
}

export const P04_COMMANDS = Object.freeze([HOSTS_READ, MODULE_PROP_READ]);
