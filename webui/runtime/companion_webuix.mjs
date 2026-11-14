/** No privileged WebUI-X/KernelSU host actions in an Android app WebView. */
export class WXEventHandler {
  on(target, event, listener) {
    if (event === 'back' && target === window && typeof listener === 'function') {
      target.addEventListener('bh-companion-back', listener);
      // Allows native Android Back to run the existing UX10 back handler.
      // At the root Home screen native may close instead of trapping Back.
      target.__bhCompanionBack = () => {
        const active = document.querySelector('.page-view[data-active="true"]');
        const dialog = Array.from(document.querySelectorAll('md-dialog')).some(d => d.open);
        const overlay = ['ux09-operation-confirm', 'ux09-operation-overlay'].some(id => {
          const element = document.getElementById(id);
          return !!element && !element.hidden;
        });
        if (active?.id === 'page-home' && !dialog && !overlay) return false;
        target.dispatchEvent(new Event('bh-companion-back'));
        return true;
      };
    }
  }
}
export class WebUI {
  startActivity() { throw new Error('External intents are unavailable in P04 preview'); }
}
export class Intent {
  static ACTION_VIEW = 'android.intent.action.VIEW';
  constructor(action) { this.action = action; }
  setData(url) { this.url = url; }
}
