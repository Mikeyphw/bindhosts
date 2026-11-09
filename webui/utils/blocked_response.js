// UX04 optional HTTP-only blocked-image controls; no arbitrary shell arguments.
import { exec } from 'kernelsu-alt';
import { moduleDirectory, showPrompt } from './util.js';

const ROOT=`sh ${moduleDirectory}/bindhosts.sh --response`;
const MODES=new Set(['off','transparent','logo']);
let busy=false;
async function call(action){
    const result=await exec(`${ROOT} ${action}`);
    if(result.errno!==0) throw new Error((result.stderr||result.stdout||'Response mode unavailable').trim());
    return result.stdout||'';
}
export async function refreshBlockedResponse(view){
    const select=view.querySelector('#response-mode');
    const line=view.querySelector('#response-status');
    if(!select || !line) return;
    try {
        const output=await call('status');
        const state=Object.fromEntries(output.trim().split('\n').filter(s=>s.includes('=')).map(s=>s.split('=',2)));
        if(!MODES.has(state.mode)) throw new Error('Invalid response mode from backend');
        select.value=state.mode;
        line.textContent=state.mode==='off'
            ? 'Off — blocked hosts use the standard connection-error response.'
            : `${state.mode==='logo'?'Bindhosts image':'Transparent GIF'} · ${state.server==='running'?'local server running':'local server not running'}. HTTP only; HTTPS remains blocked normally.`;
    } catch (error) {line.textContent=`Response mode unavailable: ${error.message}`;}
}
export function setupBlockedResponse(view, confirmAction){
    const select=view.querySelector('#response-mode');
    const button=view.querySelector('#response-apply');
    if(!select||!button)return;
    button.onclick=async()=>{
        const wanted=select.value;
        if(busy||!MODES.has(wanted))return;
        if(!await confirmAction('Change blocked-page response?', wanted==='off'
            ? 'Turn off local HTTP image responses and restore standard hosts mappings?'
            : 'Enable HTTP-only local image responses? HTTPS is not intercepted. An initial hosts Update may be required.'))return;
        busy=true;button.disabled=true;
        try {
            const result=await call(`set ${wanted}`);
            showPrompt(result.includes('BH_RESPONSE_MODE_PASS')?'Response mode applied.':'Response mode unchanged.');
        } catch(error){showPrompt(`Mode change refused: ${error.message}`,false,5000);}
        finally {busy=false;button.disabled=false;await refreshBlockedResponse(view);}
    };
}
