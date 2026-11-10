// UX04 HTTP + UX07 optional HTTPS blocked-image controls; fixed shell actions only.
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
            : `${state.mode==='logo'?'Bindhosts image':'Transparent GIF'} · HTTP ${state.server==='running'?'running':'not running'}. HTTPS is separate and opt-in.`;
        const tls=view.querySelector('#https-response-status');
        if(tls) {
          const fp=state.certificate_fingerprint_sha256;
          const validFp=typeof fp==='string' && /^[0-9A-F]{64}$/.test(fp);
          tls.textContent=`HTTPS: ${state.https_mode==='enabled'?'enabled':'off'} · TLS server: ${state.https_server==='running'?'running':'not running'} · Local CA: ${state.certificate||'absent'}${validFp?' · SHA-256: '+fp:''} · Android certificate trust: NOT verified.`;
        }
    } catch (error) {line.textContent=`Response mode unavailable: ${error.message}`;const tls=view.querySelector("#https-response-status");if(tls)tls.textContent="HTTPS status unavailable; no certificate trust claim can be made.";}
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
    setupHttpsControls(view, confirmAction);
}

// Do not take free-form shell values or install certificates without Android consent.
function setupHttpsControls(view, confirmAction){
    const actions=[
      ['https-cert-create','cert-create','Generate a new local certificate authority?',
       'The CA private key stays root-only on your device. Installing this CA into Android trust is a separate action and carries a security risk.'],
      ['https-cert-export','cert-export','Export the local CA to Downloads?',
       'Only the public certificate is exported, not its private key. Verify the fingerprint before importing it into Android Settings.'],
      ['https-response-enable','enable','Enable HTTPS images?',
       'Requires HTTP image mode, an existing private CA and certificate trust installed manually. TLS is loopback-only but may not work with pinned apps or browsers.'],
      ['https-response-disable','disable','Disable HTTPS responses?',
       'Stops the TLS server. A CA previously installed in Android remains trusted until you remove it manually.'],
      ['https-response-test','test','Run the local TLS check?',
       'This verifies the local certificate and image reply, but does not verify Android or browser trust.']
    ];
    const settings=view.querySelector('#https-certificate-settings');
    if(settings) settings.onclick=async()=>{
      if(busy || !await confirmAction('Open Android security settings?',
        'Import the public CA certificate you exported. Verify its full fingerprint before trusting it. This does not install a CA without your explicit Android consent.')) return;
      const result=await exec('am start -a android.settings.SECURITY_SETTINGS');
      if(result.errno!==0) showPrompt('Could not open Settings. Open Security settings manually.',false,5000);
    };
    for (const [id,action,title,description] of actions){
      const button=view.querySelector(`#${id}`);
      if(!button) continue;
      button.onclick=async()=>{
        if(busy || !await confirmAction(title,description)) return;
        busy=true;
        for(const [id] of actions) {const b=view.querySelector(`#${id}`);if(b)b.disabled=true;}
        try{const result=await call(`https ${action}`);showPrompt(result.trim().split('\n').slice(-2).join(' · '),true,5500);}
        catch(err){showPrompt(`HTTPS action refused: ${err.message}`,false,6000);}
        finally{busy=false;for(const [id] of actions){const b=view.querySelector(`#${id}`);if(b)b.disabled=false;}await refreshBlockedResponse(view);}
      };
    }
}
