// BH-APP01 P05: finite native read + verified hosts action bridge.
// KernelSU host remains read-only on this transport; the ordinary WebUI uses
// its own existing UX08/UX09 interfaces, not this Android adapter.
const READ_ACTIONS = new Set(['hello', 'status']);
const MANAGEMENT_ACTIONS = new Set(['config-read','config-list','config-write','catalog','tracker','packages']);
const PAGE_ACTION = 'read-page';
const NATIVE_ACTIONS = new Set([...READ_ACTIONS, 'pause','resume','update-start','update-status','update-events', PAGE_ACTION, ...MANAGEMENT_ACTIONS]);
const HOSTS = new Set(['ACTIVE', 'PAUSED', 'INACTIVE', 'DISABLED']);
const OPERATION = new Set(['IDLE', 'RUNNING', 'DONE', 'FAILED', 'INTERRUPTED']);
const STEPS = new Set(['NONE','PREPARING','DOWNLOADING','PARSED','SKIPPED_DUPLICATE_URL','DEDUPLICATING','ALLOWLIST','GENERATING','COMMITTING','DONE','UNCHANGED','FAILED','STATS']);
function operationName(name, permitted) {
  if (typeof name !== 'string' || !permitted.has(name)) throw new Error('Unsupported companion operation');
  return name;
}
export function validateReply(name, body) {
  operationName(name, NATIVE_ACTIONS);
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('Incompatible API');
  if (READ_ACTIONS.has(name)) {
    if (body.api !== 1) throw new Error('Incompatible read API');
    if (name === 'hello') {
      if (body.module !== 'bindhosts' || !Number.isSafeInteger(body.versionCode) || body.versionCode < 1 ||
          !Array.isArray(body.capabilities) || !['hello','status'].every(x => body.capabilities.includes(x))) throw new Error('Invalid module handshake');
    } else if (!HOSTS.has(body.hosts) || !OPERATION.has(body.operation)) {
      throw new Error('Invalid backend state');
    }
  } else if (name === PAGE_ACTION) {
    if (body.api !== 4 || body.action !== PAGE_ACTION ||
        Object.keys(body).sort().join(',') !== 'action,api,encoded,next,offset,selector,sha256,size,source' ||
        !MANAGEMENT_ACTIONS.has(body.source) || typeof body.selector !== 'string' ||
        !/^[A-Za-z0-9_.~-]{1,110}$/.test(body.selector) || body.selector.includes('..') ||
        !Number.isSafeInteger(body.offset) || body.offset < 0 || body.offset > 262144 ||
        !Number.isSafeInteger(body.size) || body.size < 0 || body.size > 262144 || body.offset > body.size ||
        !(body.next === null || (Number.isSafeInteger(body.next) && body.next > body.offset && body.next <= body.size)) ||
        typeof body.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(body.sha256) ||
        typeof body.encoded !== 'string' || body.encoded.length > 4096 ||
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(body.encoded))
      throw new Error('Invalid paged-read reply');
  } else if (MANAGEMENT_ACTIONS.has(name)) {
    if (body.api !== 3 || body.action !== name || Object.keys(body).sort().join(',') !== 'action,api,encoded' ||
        typeof body.encoded !== 'string' || body.encoded.length > 6500 ||
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(body.encoded))
      throw new Error('Invalid management reply');
  } else {
    if (body.api !== 2 || body.action !== name) throw new Error('Incompatible native control API');
    switch (name) {
      case 'pause': case 'resume':
        if (body.verified !== true || body.hosts !== (name === 'pause' ? 'PAUSED' : 'ACTIVE')) throw new Error('Hosts action not verified');
        break;
      case 'update-start':
        if (body.accepted !== true || !['RUNNING', 'DONE'].includes(body.operation)) throw new Error('Update launch not verified');
        break;
      case 'update-status':
        if (!OPERATION.has(body.operation) || !STEPS.has(body.step) || !['NONE','PASS','FAIL'].includes(body.receipt)) throw new Error('Invalid update state');
        if (body.operation === 'DONE' && body.receipt !== 'PASS') throw new Error('Unverified successful update');
        break;
      case 'update-events':
        if (typeof body.encoded !== 'string' || body.encoded.length > 6500 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(body.encoded)) throw new Error('Invalid bounded update event encoding');
        break;
    }
  }
  return Object.freeze(body);
}
export function kernelSuTransport(exec, moduleDirectory = '/data/adb/modules/bindhosts') {
  if (typeof exec !== 'function' || moduleDirectory !== '/data/adb/modules/bindhosts') throw new Error('Unsupported transport');
  return Object.freeze({
    async invoke(name) {
      operationName(name, READ_ACTIONS);
      const result = await exec(`sh /data/adb/modules/bindhosts/companion_api.sh ${name}`);
      if (!result || result.errno !== 0 || typeof result.stdout !== 'string' || result.stdout.length > 8192) throw new Error('Module operation unavailable');
      return validateReply(name, JSON.parse(result.stdout));
    }
  });
}
// Prevent unqualified reads even before the separate rooted allowlist revalidates them.
export function validPageRequest(arg) {
  if (typeof arg !== 'string' || arg.length > 480 || arg.includes('..')) return false;
  const match=arg.match(/^(config-read|config-list|catalog|tracker|packages)\|([A-Za-z0-9_.~-]{1,110})\|([0-9]{1,6})\|(none|[0-9a-f]{64})$/);
  if (!match || Number(match[3])>262144) return false;
  const [,source,selector]=match;
  switch(source) {
    case 'config-read': return ['sources','sources_whitelist','blacklist','whitelist','custom'].includes(selector) ||
      (/^custom_[A-Za-z0-9_.-]+\.txt$/.test(selector) && !selector.includes('..') && selector!=='custom_.txt');
    case 'config-list': return selector==='custom';
    case 'catalog': return ['status','applied-status','manual-list'].includes(selector);
    case 'tracker': return ['status','rules'].includes(selector) ||
      /^preview~[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$/.test(selector);
    case 'packages': return selector==='user';
    default: return false;
  }
}
export function nativeAppTransport(bridge, timeoutMs = 8000) {
  if (!bridge || typeof bridge.postMessage !== 'function' ||
      !Number.isSafeInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 30000) throw new Error('Invalid native bridge');
  const pending = new Map();
  let sequence = 0;
  bridge.onmessage = event => {
    let response;
    try { response = JSON.parse(event.data); } catch { return; }
    if (!response || typeof response.id !== 'string' || !pending.has(response.id)) return;
    const p = pending.get(response.id);
    pending.delete(response.id);
    clearTimeout(p.timer);
    try {
      if (response.ok !== true) throw new Error('Native bridge operation refused');
      p.resolve(validateReply(p.name, response.value));
    } catch (err) { p.reject(err); }
  };
  return Object.freeze({
    invoke(name, arg) {
      operationName(name, NATIVE_ACTIONS);
      const page = name === PAGE_ACTION;
      const management = MANAGEMENT_ACTIONS.has(name);
      if (page && !validPageRequest(arg)) throw new Error('Invalid paged-read arguments');
      if (management && (typeof arg !== 'string' || arg.length < 1 || arg.length > 13000 ||
          !/^[A-Za-z0-9_.+/=,|\-]+$/.test(arg) || arg.includes('..')))
        throw new Error('Invalid management arguments');
      if (!management && !page && arg !== undefined) throw new Error('Unexpected management arguments');
      const id = 'bh' + (++sequence).toString(36);
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => { pending.delete(id); reject(new Error('Native operation timed out')); }, timeoutMs);
        pending.set(id, {name, resolve, reject, timer});
        try { bridge.postMessage(JSON.stringify(management || page ? {id, op:name, arg} : {id, op:name})); }
        catch { clearTimeout(timer); pending.delete(id); reject(new Error('Native bridge unavailable')); }
      });
    }
  });
}
