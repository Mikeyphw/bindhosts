const key = 'bindhosts.ux.black-background.v1';
export function applyAppearance() {
    // This setting changes backgrounds only; foreground/accent colors remain dynamic.
    document.body.dataset.blackBackground = localStorage.getItem(key) === 'on' ? 'true' : 'false';
}
export function bindAppearanceControls(scope) {
    const toggle = scope.querySelector('#ui-black-bg-toggle');
    if (!toggle) return;
    toggle.checked = localStorage.getItem(key) === 'on';
    toggle.addEventListener('change', () => {
        localStorage.setItem(key, toggle.checked ? 'on' : 'off');
        applyAppearance();
    });
}
