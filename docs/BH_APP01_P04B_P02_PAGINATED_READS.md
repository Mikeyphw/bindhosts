# BH-APP01 P04B P02 — Snapshot-consistent native read paging

On PR #19, extends the green P05/P04B management transport without changing the KernelSU WebUI.

The previous v3 management API refused outputs exceeding 4,800 bytes. V4 is **read only** and pages configuration files, configured source status, TrackerGuard status/rules/previews, and installed-user-app lists. A fixed 3,072-byte page contains bytes from a 256 KiB max private snapshot; every page is bound to the same SHA-256. Concurrent changes, missing/duplicate pages, oversized datasets and unknown selectors fail closed. The WebView assembles bytes and checks the complete SHA-256 before converting UTF-8.

V3 remains the sole gated backend for mutation receipts. The new root interface never invokes update, enroll, config write or host state transitions. Old Kernelsu-alt WebUI bundles are unchanged. UTF-8 split across page boundaries is decoded only after full reassembly. Incompletely installed modules (missing V4 script) remain unqualified and refuse reads; the app does not silently retry v3 and truncate content.

Source tests include >4,800-byte configuration paging, digest drift/refusals, invalid selector and symlink negatives, and Java/JS contract checks. GitHub Actions must still prove Android compilation, strict Lint, all required workflows, and artifact generation. Android 16 physical root and UX acceptance remain pending. This does not enable the remaining backups, HTTPS settings, or general shell access.
