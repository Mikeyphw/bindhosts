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
    transport = nativeAppTransport(window.BindhostsBridge, 30000);
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
// P04B: an exact command registry, not a general shell proxy.
const CONFIG = `sh ${MOD}/hosts_config_safe.sh `;
const CATALOG = `sh ${MOD}/source_catalog.sh `;
const BATCH = `sh ${MOD}/source_catalog_batch_ux09.sh `;
const TRACKER = `sh ${MOD}/bindhosts.sh tracker `;
const BASE = '/data/adb/bindhosts';
const packageName = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$/;
const token = /^[A-Za-z0-9_-]{12,60}$/;
const encoded = /^[A-Za-z0-9+/=]{1,12000}$/;
function kind(name) {
  return ['sources','sources_whitelist','blacklist','whitelist','custom'].includes(name) ||
    (/^custom_[A-Za-z0-9_.-]+\.txt$/.test(name) && !name.includes('..'));
}
function decodeManagementResponse(base64) {
  const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
  if (bytes.length > 4800) throw new Error('Oversized management response');
  return new TextDecoder('utf-8', {fatal:true}).decode(bytes);
}
export function managementCommand(command) {
  if (typeof command !== 'string') return null;
  if (command === CATALOG + 'status') return {op:'catalog', arg:'status'};
  if (command === BATCH + 'applied-status') return {op:'catalog',arg:'applied-status'};
  if (command === BATCH + 'manual-list') return {op:'catalog',arg:'manual-list'};
  if (command.startsWith(BATCH + 'batch ')) {
    const selection=command.slice((BATCH+'batch ').length);
    if (selection==='none' || /^[a-z0-9-]+(?:,[a-z0-9-]+)*$/.test(selection))
      return {op:'catalog',arg:'batch|'+selection};
  }
  const readPrefix=`cat "${BASE}/`;
  if (command.startsWith(readPrefix) && command.endsWith('"')) {
    const file=command.slice(readPrefix.length,-1);
    const k=file.endsWith('.txt') && file.startsWith('custom_') ? file : file.endsWith('.txt') ? file.slice(0,-4) : '';
    if (kind(k)) return {op:'config-read',arg:k};
  }
  if (command === `ls ${BASE} | grep "^custom.*\\.txt$" | grep -vx "custom.txt"`)
    return {op:'config-list',arg:'custom'};
  if (command.startsWith(CONFIG)) {
    const parts=command.slice(CONFIG.length).split(' ');
    const [verb,a,b,c]=parts;
    if (['add','remove','toggle'].includes(verb) && parts.length===3 && kind(a) && encoded.test(b))
      return {op:'config-write',arg:[verb,a,b].join('|')};
    if (verb==='replace' && parts.length===4 && kind(a) && encoded.test(b) && encoded.test(c))
      return {op:'config-write',arg:[verb,a,b,c].join('|')};
    if (['stage-begin','stage-abort'].includes(verb) && parts.length===2 && token.test(a))
      return {op:'config-write',arg:[verb,a].join('|')};
    if (verb==='stage-chunk' && parts.length===3 && token.test(a) && encoded.test(b))
      return {op:'config-write',arg:[verb,a,b].join('|')};
    if (verb==='stage-commit' && parts.length===3 && token.test(a) && kind(b))
      return {op:'config-write',arg:[verb,a,b].join('|')};
    if (verb==='delete-custom' && parts.length===2 && /^custom_[A-Za-z0-9_.-]+\.txt$/.test(a) && !a.includes('..'))
      return {op:'config-write',arg:[verb,a].join('|')};
    if (verb==='rename-custom' && parts.length===3 && kind(a) && kind(b) && a.startsWith('custom_') && b.startsWith('custom_'))
      return {op:'config-write',arg:[verb,a,b].join('|')};
    if (verb==='import-custom' && parts.length===3 && encoded.test(a) && kind(b) && b.startsWith('custom_'))
      return {op:'config-write',arg:[verb,a,b].join('|')};
  }
  if (command === TRACKER + 'json status') return {op:'tracker',arg:'status'};
  if (command === TRACKER + 'json rules') return {op:'tracker',arg:'rules'};
  if (command === 'pm list packages -3') return {op:'packages',arg:'user'};
  if (command.startsWith(TRACKER)) {
    const parts=command.slice(TRACKER.length).split(' ');
    const [verb,pkg]=parts;
    if (['preview','enroll','unenroll','exclude','include'].includes(verb) &&
        parts.length===2 && packageName.test(pkg)) return {op:'tracker',arg:verb+'|'+pkg};
    if (verb==='monitor' && parts.length===2 && ['enable','disable','once'].includes(pkg))
      return {op:'tracker',arg:'monitor|'+pkg};
  }
  return null;
}

// P04B P02: SHA-256 pinned bounded snapshot paging for read-only UX10 commands.
// Never paginate writes: v3 retains fixed receipts and explicit transaction gates.
const PAGED_READS = new Set(['config-read','config-list','packages']);
const BACKUP = `sh ${MOD}/config_backup_safe.sh `;
const DIAGNOSTICS = `sh ${MOD}/ux05_diagnostics.sh `;
const RESPONSE = `sh ${MOD}/bindhosts.sh --response `;
const SNAPSHOT_ID = /^bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$/;
const ARCHIVE_NAME = /^bindhosts-backup-bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}\.tar$/;
// This registry follows UX05/06/07 fixed verbs. The normal KernelSU WebUI
// retains its own backend. No user value becomes an executable shell command.
export function moreCommand(command) {
  if (typeof command !== 'string') return null;
  if (command.startsWith(BACKUP)) {
    const args = command.slice(BACKUP.length).split(' ');
    if (args.length === 1 && ['status','health','list','imports','create'].includes(args[0]))
      return {op:'backup',arg:args[0]};
    if (args.length === 2 && ['verify','preview','restore','export'].includes(args[0]) && SNAPSHOT_ID.test(args[1]))
      return {op:'backup',arg:args[0]+'~'+args[1]};
    if (args.length === 2 && args[0] === 'import' && ARCHIVE_NAME.test(args[1]))
      return {op:'backup',arg:'import~'+args[1]};
    return null;
  }
  if (command.startsWith(DIAGNOSTICS)) {
    const args=command.slice(DIAGNOSTICS.length).split(' ');
    if (args.length === 1 && ['status','export'].includes(args[0])) return {op:'diagnostics',arg:args[0]};
    if (args.length === 2 && args[0] === 'history' && /^[1-9][0-9]?$|^100$/.test(args[1]))
      return {op:'diagnostics',arg:'history~'+args[1]};
    return null;
  }
  if (command.startsWith(RESPONSE)) {
    const args=command.slice(RESPONSE.length).split(' ');
    if (args.length === 1 && args[0] === 'status') return {op:'response',arg:'status'};
    if (args.length === 2 && args[0] === 'set' && ['off','transparent','logo'].includes(args[1]))
      return {op:'response',arg:'set~'+args[1]};
    if (args.length === 2 && args[0] === 'https' &&
        ['cert-create','cert-export','enable','disable','test'].includes(args[1]))
      return {op:'response',arg:'https~'+args[1]};
  }
  return null;
}
function moreRead(op,arg) {
  if (op==='backup' && (['status','health','list','imports'].includes(arg) ||
      /^(verify|preview)~bh-[0-9]{8}T[0-9]{6}-[A-Za-z0-9]{6}$/.test(arg))) return arg;
  if (op==='diagnostics' && (arg==='status' || /^history~(?:[1-9][0-9]?|100)$/.test(arg))) return arg;
  if (op==='response' && arg==='status') return arg;
  return null;
}
function pagedSelector(op,arg) {
  if (PAGED_READS.has(op)) return arg;
  if (op==='catalog' && ['status','applied-status','manual-list'].includes(arg)) return arg;
  if (op==='tracker' && ['status','rules'].includes(arg)) return arg;
  if (op==='tracker' && arg.startsWith('preview|')) {
    const pkg=arg.slice(8);
    if (packageName.test(pkg)) return 'preview~'+pkg;
  }
  return null;
}
function decodePage(encoded) {
  const binary=atob(encoded);
  if (binary.length>3072) throw new Error('Read page exceeds bound');
  return Uint8Array.from(binary,c=>c.charCodeAt(0));
}
export async function readPaginated(op,selector) {
  if (!['config-read','config-list','catalog','tracker','packages','backup','diagnostics','response'].includes(op) ||
      typeof selector!=='string' || !/^[A-Za-z0-9_.~-]{1,110}$/.test(selector) || selector.includes('..'))
    throw new Error('Unqualified paged-read source');
  let cursor=0, hash='none', size=-1;
  const pages=[];
  for (let round=0;round<87;round++) {
    const response=await native().invoke('read-page',`${op}|${selector}|${cursor}|${hash}`);
    if (response.source!==op || response.selector!==selector || response.offset!==cursor)
      throw new Error('Page source mismatch');
    if (hash!=='none' && hash!==response.sha256) throw new Error('Snapshot drift');
    if (size!==-1 && size!==response.size) throw new Error('Snapshot size drift');
    hash=response.sha256; size=response.size;
    const chunk=decodePage(response.encoded);
    if (chunk.length!==Math.min(3072,size-cursor)) throw new Error('Page byte count mismatch');
    if (response.next!==null && response.next!==cursor+chunk.length)
      throw new Error('Noncontiguous read page');
    if (response.next===null && cursor+chunk.length!==size)
      throw new Error('Premature end of snapshot');
    pages.push(chunk);
    cursor+=chunk.length;
    if (response.next===null) {
      const all=new Uint8Array(size);let offset=0;
      for(const b of pages){all.set(b,offset);offset+=b.length;}
      if (!globalThis.crypto?.subtle) throw new Error('Missing SHA-256 verifier');
      const actual=Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',all)))
        .map(x=>x.toString(16).padStart(2,'0')).join('');
      if(actual!==hash) throw new Error('Corrupted native read');
      return new TextDecoder('utf-8',{fatal:true}).decode(all);
    }
    if (cursor>=size) throw new Error('Invalid paged continuation');
  }
  throw new Error('Read exceeds page-count bound');
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
    const more = moreCommand(command);
    if (more) {
      const selector=moreRead(more.op,more.arg);
      if (selector!==null) return success(await readPaginated(more.op,selector));
      const result=await native().invoke(more.op,more.arg);
      return success(decodeManagementResponse(result.encoded));
    }
    // P04B: only exact UX10 commands are mapped; arguments are passed as data
    // through the v3 validated native boundary, never executed as shell text.
    const management = managementCommand(command);
    if (management) {
      const selector=pagedSelector(management.op,management.arg);
      if(selector!==null) return success(await readPaginated(management.op,selector));
      const response = await native().invoke(management.op, management.arg);
      return success(decodeManagementResponse(response.encoded));
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
