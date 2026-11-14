/** P06: companion-build-only transformation of the existing UX10 file picker.
 * KernelSU's default Vite build never loads this plugin or modifies its source.
 * Refuse upstream selector drift rather than silently shipping shell file browsing. */
const NEEDLE = 'getFilePath: async function (type) {';
const HOOK = `getFilePath: async function (type) {
        if (type === 'txt' && typeof window.__bhCompanionPickText === 'function') {
            try { return await window.__bhCompanionPickText(); }
            catch (error) {
                console.error('Native document selection unavailable:', error);
                return null; // Cancel or invalid document: no root write.
            }
        }`;

export function injectSafPicker(source) {
  if (typeof source !== 'string' || source.split(NEEDLE).length !== 2)
    throw new Error('BH_APP01_P06_REFUSED: UX10 FileSelector source drift');
  return source.replace(NEEDLE, HOOK);
}

export function companionSafPickerPlugin() {
  return Object.freeze({
    name: 'bh-app01-p06-saf-text-import',
    enforce: 'pre',
    transform(source, id) {
      if (!/[/\\]utils[/\\]file_selector\.js(?:\?.*)?$/.test(id)) return null;
      return {code: injectSafPicker(source), map: null};
    },
  });
}
