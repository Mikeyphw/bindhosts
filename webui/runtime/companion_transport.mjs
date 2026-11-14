// BH-APP01: finite read-only typed transport. The existing WebUI is not yet
// rerouted through this module; P02 completes the migration after parity tests.
const ACTIONS = new Set(['hello', 'status']);
const HOSTS = new Set(['ACTIVE', 'PAUSED', 'INACTIVE', 'DISABLED']);
const OPERATION = new Set(['IDLE', 'RUNNING', 'DONE', 'FAILED', 'INTERRUPTED']);

function operationName(name) {
  if (typeof name !== 'string' || !ACTIONS.has(name)) throw new Error('Unsupported companion operation');
  return name;
}
export function validateReply(name, body) {
  operationName(name);
  if (!body || typeof body !== 'object' || Array.isArray(body) || body.api !== 1) throw new Error('Incompatible API');
  if (name === 'hello') {
    if (body.module !== 'bindhosts' || !Number.isSafeInteger(body.versionCode) || body.versionCode < 1 ||
        !Array.isArray(body.capabilities) || !['hello','status'].every(x => body.capabilities.includes(x))) throw new Error('Invalid module handshake');
  } else if (!HOSTS.has(body.hosts) || !OPERATION.has(body.operation)) {
    throw new Error('Invalid backend state');
  }
  return Object.freeze(body);
}
export function kernelSuTransport(exec, moduleDirectory = '/data/adb/modules/bindhosts') {
  if (typeof exec !== 'function' || moduleDirectory !== '/data/adb/modules/bindhosts') throw new Error('Unsupported transport');
  return Object.freeze({
    async invoke(name) {
      operationName(name);
      // A literal allowlisted token is the ONLY variable that reaches the command.
      const result = await exec(`sh /data/adb/modules/bindhosts/companion_api.sh ${name}`);
      if (!result || result.errno !== 0 || typeof result.stdout !== 'string' || result.stdout.length > 8192) throw new Error('Module operation unavailable');
      return validateReply(name, JSON.parse(result.stdout));
    }
  });
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
    invoke(name) {
      operationName(name);
      const id = 'bh' + (++sequence).toString(36);
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => { pending.delete(id); reject(new Error('Native operation timed out')); }, timeoutMs);
        pending.set(id, {name, resolve, reject, timer});
        try { bridge.postMessage(JSON.stringify({id, op:name})); }
        catch { clearTimeout(timer); pending.delete(id); reject(new Error('Native bridge unavailable')); }
      });
    }
  });
}
