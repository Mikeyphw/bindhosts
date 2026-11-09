# UX05 — Local activity and redacted diagnostics

Base: `43b67ec1fed8ada7f797021be0df23889ab34130` (master, after UX03/UX04 merge).
Proposed module version: `v2.1.5-tg.0.8` / `21608`.

## Scope

- **More → Activity & diagnostics** is an additional page, without enlarging the five-icon bottom navigation. A compact overview shows event count, recorded failure count, pending journal status, source count (not source URLs), the saved HTTP image mode and whether TrackerGuard polling is enabled.
- Recent receipts (most recent 100, filterable by result) show timestamp, area, action, outcome, safe code and actionable instructions. All rendering uses DOM `textContent` and static messages.
- Root-only backend `module/ux05_diagnostics.sh`: `status`, `history [1..100]`, `record AREA ACTION RESULT CODE` (strictly allowlisted), and **user-triggered** `export`. No arbitrary filesystem paths, free-form detail, package names, URLs or hostnames enter the history API. The backend never runs `su` or reconfigures protection.
- Persistent history: `/data/adb/bindhosts/diagnostics/receipts.psv`, private directory mode `0700`, file `0600`, newest **400** receipts. All writes are guarded by a directory lock and rotation is same-directory atomic. Read-only `status` and `history` do not create any directories or lock.
- The existing CLI captures successful/failed hosts updates, reset/toggle/instant allowlisting, explicit TrackerGuard actions, and HTTP response-mode operations. The journaled writer records successful atomic/in-place commits, completed recovery and failed recovery. Boot failure to start the HTTP responder is also recorded.
- **Diagnostic export is opt-in** and writes a JSON file to shared Downloads after explicit confirmation. It contains operation timestamps, predefined status codes, summary counts and module version. It does **not** include raw source URLs, hosts file, DNS queries, private rule files, package identities, IFW XML, root logs or crash stacks. Because timestamps can still be sensitive, share deliberately.

## Safety boundaries

- Receipt failures are deliberately non-fatal. A full disk or stale diagnostics lock must not change the return code of a hosts write or TrackerGuard action. The UI may therefore show fewer receipts than actual operations; event history is **operational telemetry, not an immutable audit ledger**.
- Older unstructured logs are not migrated, and previous milestones cannot be retroactively reconstructed.
- No automatic permission grants, network telemetry, monitoring enrolment or responder activation. Existing TrackerGuard receiver-only policy and host blocklist rules remain untouched.
- `$TMPDIR` is used for build, extraction and automated-test scratch space. The private on-device diagnostics directory and hosts journal persist by design; the receipt rotation file is created beside its destination to preserve atomic rename semantics.

## Validation

```sh
sh -n module/ux05_diagnostics.sh
python3 tests/test_ux05_diagnostics.py
python3 tests/test_ux05_contract.py
node --check webui/page/activity/activity.js
```

CI also runs existing UX01-UX04, TrackerGuard and native build jobs. The overlay is source-pinned and must pass full local validation before it commits or pushes. Android acceptance remains a separate gate.

## Device smoke test (after installation)

```sh
su -c 'sh /data/adb/modules/bindhosts/ux05_diagnostics.sh status'
su -c 'sh /data/adb/modules/bindhosts/ux05_diagnostics.sh history 10'
```

In the KernelSU WebUI, navigate **More → Activity & diagnostics**, refresh, check filters and export a redacted JSON report only if needed. Do not mistake `response_mode=off` or `monitor_enabled=false` for failures: they are intended default settings.
