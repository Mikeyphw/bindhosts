// UX02: the UI never interpolates file content or paths into a shell program.
// All variable text travels as base64 through a fixed root-side verb interface.
import { exec } from 'kernelsu-alt';

const backend = '/data/adb/modules/bindhosts/hosts_config_safe.sh';
const allowedKinds = new Set(['sources', 'sources_whitelist', 'blacklist', 'whitelist', 'custom']);
const namePattern = /^custom_[A-Za-z0-9_.-]+\.txt$/;

function kind(value) {
    if (!allowedKinds.has(value) && !namePattern.test(value)) {
        throw new Error('Unsupported configuration filename');
    }
    return value;
}
function atom(value) {
    if (!/^[A-Za-z0-9_./+=-]+$/.test(value)) {
        throw new Error('Invalid backend argument');
    }
    return value;
}
function encode(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = '';
    for (let i = 0; i < bytes.length; i += 4096) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 4096));
    }
    return btoa(binary);
}
async function invoke(verb, ...arguments_) {
    const tokens = [atom(verb), ...arguments_.map(atom)];
    const result = await exec(`sh ${backend} ${tokens.join(' ')}`);
    if (result.errno !== 0) throw new Error((result.stderr || result.stdout || 'Backend error').trim());
    return result.stdout;
}
export const secureAdd = (file, line) => invoke('add', kind(file), encode(line));
export const secureRemove = (file, line) => invoke('remove', kind(file), encode(line));
export const secureToggle = (file, line) => invoke('toggle', kind(file), encode(line));
export const secureReplaceLine = (file, oldLine, newLine) => invoke('replace', kind(file), encode(oldLine), encode(newLine));
export const secureDeleteCustom = file => invoke('delete-custom', kind(file));
export const secureRenameCustom = (from, to) => invoke('rename-custom', kind(from), kind(to));
export const secureImportCustom = (source, destination) => invoke('import-custom', encode(source), kind(destination));
export const secureFileSize = async file => Number((await invoke('size', kind(file))).trim());

function txid() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return 'ux02_' + Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}
// The maximum editor input is 2 MiB; split it into safe ~6 KiB shell arguments.
// A failed chunk never touches the real config file; commit is the sole write.
export async function secureSaveFile(file, content) {
    kind(file);
    const bytes = new TextEncoder().encode(content);
    if (bytes.length > 2 * 1024 * 1024) throw new Error('Editor maximum: 2 MiB');
    const token = txid();
    await invoke('stage-begin', token);
    try {
        for (let i = 0; i < bytes.length; i += 6000) {
            let binary = '';
            const slice = bytes.subarray(i, i + 6000);
            for (let j = 0; j < slice.length; j += 4096) {
                binary += String.fromCharCode(...slice.subarray(j, j + 4096));
            }
            await invoke('stage-chunk', token, btoa(binary));
        }
        await invoke('stage-commit', token, file);
    } catch (error) {
        try { await invoke('stage-abort', token); } catch { /* preserved original file */ }
        throw error;
    }
}
