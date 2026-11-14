(() => {
  'use strict';
  const bridge = window.BindhostsBridge;
  const hello = document.getElementById('hello');
  const state = document.getElementById('state');
  const operation = document.getElementById('operation');
  const refresh = document.getElementById('refresh');
  let serial = 0;
  const pending = new Map();
  if (!bridge || typeof bridge.postMessage !== 'function') {
    hello.textContent = 'Secure Android WebView bridge unavailable';
    state.textContent = 'Unavailable';
    refresh.disabled = true;
    return;
  }
  bridge.onmessage = event => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    const current = pending.get(message.id);
    if (!current) return;
    pending.delete(message.id);
    clearTimeout(current.timer);
    if (message.ok === true) current.resolve(message.value);
    else current.reject(new Error('Root denied or module unavailable'));
  };
  function invoke(op) {
    if (op !== 'hello' && op !== 'status') return Promise.reject(new Error('Unsupported operation'));
    const id = 'bh' + (++serial).toString(36);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('Timed out')); }, 9000);
      pending.set(id, {timer, resolve, reject});
      bridge.postMessage(JSON.stringify({id, op}));
    });
  }
  async function load() {
    refresh.disabled = true;
    state.textContent = 'Checking…';
    try {
      const result = await invoke('status');
      if (result.api !== 1 || !['ACTIVE','PAUSED','INACTIVE','DISABLED'].includes(result.hosts) ||
        !['IDLE','RUNNING','DONE','FAILED','INTERRUPTED'].includes(result.operation)) throw new Error('Unrecognized response');
      state.textContent = result.hosts;
      operation.textContent = 'Hosts update: ' + result.operation;
    } catch {
      state.textContent = 'Unavailable';
      operation.textContent = 'Check root permission, module installation and API compatibility.';
    } finally { refresh.disabled = false; }
  }
  refresh.addEventListener('click', load);
  invoke('hello').then(result => {
    if (result.api !== 1 || result.module !== 'bindhosts') throw new Error('Invalid handshake');
    hello.textContent = 'Module versionCode ' + result.versionCode + ' · API v1';
  }).catch(() => { hello.textContent = 'Module unavailable or incompatible'; });
  load();
})();
