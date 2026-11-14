"""P06 source contracts: real SAF, safe insets, backend preservation, no new root shell."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT/'android/companion/app/src/main/java/com/mikeyphw/bindhosts'

class P06Native(unittest.TestCase):
    def test_native_chooser_requires_actual_user_document_and_private_staging(self):
        picker = (ANDROID/'NativeImportPicker.java').read_text()
        for fragment in ['"content".equals(uri.getScheme())', 'getContentResolver().openInputStream(uri)',
            'OpenableColumns.DISPLAY_NAME', 'MAX_BYTES = 2 * 1024 * 1024', 'target.createNewFile()',
            'getExternalCacheDir()', 'MAX_FILES = 32', 'file.lastModified() < cutoff',
            'getCanonicalPath()', 'Files.isSymbolicLink', 'Unsupported document URI',
            'Document contains unsupported characters']:
            self.assertIn(fragment,picker)
        for forbidden in ['getDataColumn(', 'MediaStore.Images', 'Environment.getExternalStorageDirectory()',
                          'ProcessBuilder(', 'Runtime.getRuntime()', 'startActivity(', 'file://']:
            self.assertNotIn(forbidden,picker)

    def test_bridge_picker_path_exits_only_by_content_uri_and_fixed_op(self):
        activity=(ANDROID/'MainActivity.java').read_text()
        for required in ['"pick-text".equals(op)', 'request.length() != 2', 'runOnUiThread(() -> openTextPicker(id, replyProxy))',
           'new Intent(Intent.ACTION_OPEN_DOCUMENT)', 'Intent.CATEGORY_OPENABLE',
           'startActivityForResult(intent, PICK_TEXT_REQUEST)', 'NativeImportPicker.copy(this, selected)',
           'completePicker(null)', 'onActivityResult(', 'pickerId != null',
           'value.put("api", 6)', 'value.put("path", path)', 'pickerId = null;',
           'if (!destroyed && !isFinishing()) replyProxy.postMessage(response.toString());']:
            self.assertIn(required,activity)
        self.assertIn('worker.execute(() -> {',activity)
        self.assertIn('NativeImportPicker.copy(this, selected)',activity)
        self.assertIn('runOnUiThread(() -> { if (!destroyed) completePicker(resultPath); });',activity)
        self.assertNotIn('addJavascriptInterface(',activity)
        self.assertNotIn('setAllowFileAccess(true)',activity)
        self.assertNotIn('android.permission.INTERNET',(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text())

    def test_rotation_resize_edge_safe_back_and_lifecycle(self):
        manifest=(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text()
        activity=(ANDROID/'MainActivity.java').read_text()
        self.assertIn('android:windowSoftInputMode="adjustResize"',manifest)
        self.assertIn('android:configChanges="orientation|screenSize|keyboardHidden|uiMode"',manifest)
        for required in ['SOFT_INPUT_ADJUST_RESIZE','Build.VERSION.SDK_INT >= 35', 'WindowInsets.Type.systemBars()',
             'WindowInsets.Type.ime()', 'Math.max(bars.bottom, ime.bottom)', 'onConfigurationChanged(Configuration config)',
             'frame.requestApplyInsets()', '"Local UX10 bundle unavailable. No remote fallback was loaded."',
             'onReceivedError(WebView view, WebResourceRequest request, WebResourceError error)',
             'pageLoadError', 'private boolean destroyed = false;', 'worker.shutdownNow()',
             'web.stopLoading()', 'web.destroy()', 'intent.setAction(null)']:
            self.assertIn(required,activity)
        self.assertIn('window.__bhCompanionBack()',activity)
        self.assertIn('assets/ux10/index.html',activity)
        self.assertIn('WebResourceResponse("text/plain", "UTF-8", 403',activity)

    def test_companion_only_build_transform_and_contract(self):
        normal=(ROOT/'webui/vite.config.js')
        companion=(ROOT/'webui/vite.companion.config.js').read_text()
        transformer=(ROOT/'webui/runtime/companion_saf_picker.mjs').read_text()
        source=(ROOT/'webui/runtime/companion_kernelsu_alt.mjs').read_text()
        contract=json.loads((ROOT/'contracts/bh-app01-v6.json').read_text())
        self.assertIn('companionSafPickerPlugin()',companion)
        self.assertIn('companion_saf_picker.mjs',companion)
        self.assertIn('getFilePath: async function (type) {',transformer)
        self.assertIn("type === 'txt'",transformer)
        self.assertIn("typeof window.__bhCompanionPickText === 'function'",transformer)
        self.assertIn("native().invoke('pick-text')",source)
        self.assertEqual(contract['api_version'],6)
        self.assertEqual(contract['allowed_operations'],['pick-text'])
        self.assertFalse(contract['arbitrary_shell_supported'])
        if normal.exists():
            self.assertNotIn('companionSafPickerPlugin',normal.read_text())

    def test_hosted_lint_not_disabled(self):
        ci=(ROOT/'.github/workflows/bh-app01-foundation.yml').read_text()
        gradle=(ROOT/'android/companion/app/build.gradle.kts').read_text()
        self.assertIn('test_bh_app01_p06_picker.mjs',ci)
        self.assertIn('bh-app01-v6.json',ci)
        self.assertIn(':app:lintDebug',ci)
        self.assertNotIn('abortOnError = false',ci)
        self.assertNotIn('abortOnError = false',gradle)
        self.assertNotIn('disable.add("StartActivityAndCollapseDeprecated")',gradle)

if __name__=='__main__':unittest.main()
