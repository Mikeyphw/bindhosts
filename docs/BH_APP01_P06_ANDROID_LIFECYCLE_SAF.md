# BH-APP01 P06 — Android UX/lifecycle and SAF .txt import

Source-pinned to P04B P03 (PR #19), without modifying the original KernelSU Vite config.

## Consolidated implementation

- Android 15–16 system-bar/IME-safe insets, `adjustResize`, orientation and uiMode changes that preserve the WebView and in-progress UX10 route state rather than recreating its DOM. Legacy API 26–34 uses the existing platform window-fitting behavior.
- Native Back retains UX10's managed-dialog/navigation handler, with a fail-closed loading-error fallback. WebView main-frame load status is displayed outside WebView, and no remote fallback is allowed.
- Android `ACTION_OPEN_DOCUMENT` for **custom `.txt` imports** (UX10 `FileSelector.getFilePath('txt')` only). Vite adds the hook **only** for the Android companion build. The ordinary KernelSU WebUI JavaScript source and build remain unchanged.
- Selected `content://` document is read through ContentResolver, never via a provider's purported path. The app copies at most 2 MiB of printable ASCII+LF to a unique file in its own external-cache `imports/` directory. Binary, NUL/CR/tab, symlink, traversal, non-.txt, inaccessible storage, concurrent selection and oversized documents refuse. Old app-owned imports can be pruned after 60 minutes; at most 32 staged files are permitted.
- The resulting path must match a strict v6 receipt and still passes through UX02's existing base64-encoded safe `import-custom` command and root-side file verification. Cancelling or refusing a chooser does not invoke a root write. No new storage, internet or root privileges.
- Android activity destruction cancels its pending picker, stops the bridge executor and prevents UI callback delivery to a destroyed WebView. Native update QS intent is consumed once to avoid accidental repeated confirmation after recreation.

## Deliberate limits and release gates

The new SAF picker supports only custom `.txt` hosts imports, **not** restoring arbitrary archives or accessing external app files. User-selected backup imports still use the existing, narrowly validated Downloads workflow. File naming and ASCII restrictions are intentional; a source file that does not satisfy the existing UX02 editor should be refused, not normalized silently. No automatic Android CA installation, unattended hosts changes, screenshot publication, auto-privilege, broad storage access, or network fallback. Strict hosted Android Lint, device rotation/IME and OS chooser tests and physical Android 16 rooted read/write+rollback acceptance are still mandatory before release.
