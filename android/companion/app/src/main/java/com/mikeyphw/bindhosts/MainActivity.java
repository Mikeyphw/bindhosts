package com.mikeyphw.bindhosts;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Configuration;
import android.os.Build;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.view.View;
import android.webkit.WebResourceError;
import android.graphics.Color;
import android.util.TypedValue;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.webkit.JavaScriptReplyProxy;
import androidx.webkit.WebMessageCompat;
import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import org.json.JSONObject;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Shared UX10 UI with a finite, versioned native hosts-control bridge. */
public final class MainActivity extends Activity {
    public static final String ACTION_CONFIRM_UPDATE = "com.mikeyphw.bindhosts.CONFIRM_UPDATE";
    private static final String P07_AUDIT_TAG = "BH_APP01_P07";
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private static final int PICK_TEXT_REQUEST = 6406;
    private ExecutorService worker;
    private WebView web;
    private LinearLayout frame;
    private TextView loadStatus;
    private boolean destroyed = false;
    private boolean pageLoadError = false;
    // A QS launch may arrive during onCreate, before Android reports RESUMED.
    // Never show a modal dialog synchronously in that lifecycle transition.
    private boolean activityResumed = false;
    private boolean pendingUpdateConfirmation = false;
    private boolean updateConfirmationScheduled = false;
    private android.app.AlertDialog updateConfirmation;
    private String pickerId;
    private JavaScriptReplyProxy pickerReply;

    @Override public void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        worker = Executors.newSingleThreadExecutor();
        web = new WebView(this);
        // An out-of-WebView disclosure cannot be hidden by a bundled page.
        frame = new LinearLayout(this);
        frame.setOrientation(LinearLayout.VERTICAL);
        frame.setBackgroundColor(Color.rgb(18, 20, 24));
        TextView disclaimer = new TextView(this);
        disclaimer.setText("UX10 shared UI · VERIFIED HOSTS CONTROLS · bounded Rules, Sources and TrackerGuard operations · verified backup/HTTPS/Activity actions; explicit user confirmation required");
        disclaimer.setTextColor(Color.WHITE);
        disclaimer.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        disclaimer.setPadding(18, 12, 18, 12);
        disclaimer.setBackgroundColor(Color.rgb(47, 52, 64));
        frame.addView(disclaimer, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        loadStatus = new TextView(this);
        loadStatus.setTextColor(Color.WHITE);
        loadStatus.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        loadStatus.setPadding(18, 8, 18, 8);
        loadStatus.setText("Loading local UX10 interface…");
        loadStatus.setBackgroundColor(Color.rgb(35, 45, 59));
        frame.addView(loadStatus, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        frame.addView(web, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        getWindow().setStatusBarColor(Color.rgb(18, 20, 24));
        getWindow().setNavigationBarColor(Color.rgb(18, 20, 24));
        if (Build.VERSION.SDK_INT >= 35) {
            // Android 15+ enforces edge-to-edge: protect both system bars and IME.
            frame.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                android.graphics.Insets ime = insets.getInsets(WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime.bottom));
                return insets;
            });
        }
        setContentView(frame);
        frame.requestApplyInsets();
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setDomStorageEnabled(true); // UX10 locale and appearance preferences only
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                pageLoadError = false;
                if (!destroyed && loadStatus != null) {
                    loadStatus.setText("Loading local UX10 interface…");
                    loadStatus.setVisibility(View.VISIBLE);
                }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!destroyed && !pageLoadError && loadStatus != null) loadStatus.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame() && !destroyed && loadStatus != null) {
                    pageLoadError = true;
                    loadStatus.setText("Local UX10 bundle unavailable. No remote fallback was loaded.");
                    loadStatus.setVisibility(View.VISIBLE);
                }
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                // Refuse remote subresources even when WebView later changes settings.
                if (!"https".equals(url.getScheme()) || !"appassets.androidplatform.net".equals(url.getHost())
                        || !url.getPath().startsWith("/assets/ux10/")) {
                    return new WebResourceResponse("text/plain", "UTF-8", 403, "Forbidden",
                            java.util.Collections.emptyMap(), new java.io.ByteArrayInputStream(new byte[0]));
                }
                return loader.shouldInterceptRequest(url);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                return !request.isForMainFrame() || !ORIGIN.equals(uri.getScheme() + "://" + uri.getHost())
                        || !uri.getPath().startsWith("/assets/ux10/");
            }
        });
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            web.loadData("Bridge feature unavailable on this WebView", "text/plain", "UTF-8");
            return;
        }
        WebViewCompat.addWebMessageListener(web, "BindhostsBridge", Collections.singleton(ORIGIN),
                (view, message, sourceOrigin, isMainFrame, replyProxy) -> {
            if (!isMainFrame || !ORIGIN.equals(sourceOrigin.toString()) ||
                    message.getType() != WebMessageCompat.TYPE_STRING) return;
            String data = message.getData();
            if (data == null || data.length() > 18500) return;
            final String id;
            final String op;
            final String argument;
            final boolean management;
            final boolean more;
            try {
                JSONObject request = new JSONObject(data);
                id = request.getString("id");
                op = request.getString("op");
                more = RootRunner.isMoreOperation(op);
                if ("pick-text".equals(op)) {
                    if (request.length() != 2 || !id.matches("bh[a-z0-9]{1,16}")) return;
                    runOnUiThread(() -> openTextPicker(id, replyProxy));
                    return;
                }
                management = RootRunner.isManagementOperation(op) || more || "read-page".equals(op);
                if (!id.matches("bh[a-z0-9]{1,16}")) return;
                if (management) {
                    if (request.length() != 3 || !request.has("arg")) return;
                    argument = request.getString("arg");
                    if (!("read-page".equals(op) ? RootRunner.validPageArgument(argument) :
                            more ? RootRunner.validMoreArgument(argument) :
                            RootRunner.validManagementArgument(argument))) return;
                } else {
                    if (request.length() != 2 || (!"hello".equals(op) && !"status".equals(op) &&
                            !"pause".equals(op) && !"resume".equals(op) &&
                            !"update-start".equals(op) && !"update-status".equals(op) && !"update-events".equals(op))) return;
                    argument = "";
                }
            } catch (Exception ignored) { return; }
            if (destroyed || worker.isShutdown()) return;
            worker.execute(() -> {
                JSONObject response = new JSONObject();
                try {
                    response.put("id", id);
                    response.put("ok", true);
                    response.put("value", "read-page".equals(op) ? RootRunner.page(argument) :
                            more ? RootRunner.more(op, argument) :
                            management ? RootRunner.manage(op, argument) :
                            (("hello".equals(op) || "status".equals(op))
                            ? RootRunner.read(op) : RootRunner.control(op)));
                } catch (Exception denied) {
                    try { response.put("id", id); response.put("ok", false); } catch (Exception ignored) { return; }
                }
                runOnUiThread(() -> {
                    if (!destroyed && !isFinishing()) replyProxy.postMessage(response.toString());
                });
            });
        });
        web.loadUrl(ORIGIN + "/assets/ux10/index.html");
        consumeUpdateIntent(getIntent());
    }
    @Override protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        consumeUpdateIntent(intent);
    }
    @Override protected void onResume() {
        super.onResume();
        activityResumed = true;
        scheduleUpdateConfirmation();
    }
    @Override protected void onPause() {
        activityResumed = false;
        super.onPause();
    }
    private void consumeUpdateIntent(Intent intent) {
        if (intent != null && ACTION_CONFIRM_UPDATE.equals(intent.getAction())) {
            intent.setAction(null); // Consume once: no repeated modal on recreation.
            pendingUpdateConfirmation = true;
            android.util.Log.i(P07_AUDIT_TAG, "QS_CONFIRM_INTENT_ACCEPTED");
            scheduleUpdateConfirmation();
        }
    }
    private void scheduleUpdateConfirmation() {
        if (destroyed || !activityResumed || !pendingUpdateConfirmation ||
                updateConfirmationScheduled || frame == null) return;
        updateConfirmationScheduled = true;
        // Post until after onCreate/onResume returns to the main event loop.
        // Showing AlertDialog inside onCreate blocked ActivityScenario at PRE_ON_CREATE.
        frame.post(() -> {
            updateConfirmationScheduled = false;
            if (destroyed || !activityResumed || !pendingUpdateConfirmation ||
                    isFinishing() || isDestroyed()) return;
            pendingUpdateConfirmation = false;
            showConfirmUpdate();
        });
    }

    private void openTextPicker(String id, JavaScriptReplyProxy reply) {
        if (destroyed || isFinishing()) return;
        if (pickerId != null) {
            sendPickerResult(id, reply, null);
            return;
        }
        pickerId = id;
        pickerReply = reply;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES,
                new String[]{"text/plain", "application/octet-stream"});
        try {
            startActivityForResult(intent, PICK_TEXT_REQUEST);
        } catch (RuntimeException denied) {
            completePicker(null);
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_TEXT_REQUEST || pickerId == null) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            completePicker(null);
            return;
        }
        final Uri selected = data.getData();
        // Providers can be slow or blocked; never copy a document on Android's UI thread.
        if (destroyed || worker == null || worker.isShutdown()) return;
        try {
            worker.execute(() -> {
                String selectedPath = null;
                try { selectedPath = NativeImportPicker.copy(this, selected); }
                catch (Exception denied) { /* Malformed, binary or oversized document: no root call. */ }
                final String resultPath = selectedPath;
                runOnUiThread(() -> { if (!destroyed) completePicker(resultPath); });
            });
        } catch (java.util.concurrent.RejectedExecutionException unavailable) {
            completePicker(null);
        }
    }

    private void completePicker(String path) {
        String id = pickerId;
        JavaScriptReplyProxy reply = pickerReply;
        pickerId = null;
        pickerReply = null;
        if (id != null && reply != null && !destroyed) sendPickerResult(id, reply, path);
    }

    private void sendPickerResult(String id, JavaScriptReplyProxy reply, String path) {
        if (destroyed || web == null) return;
        JSONObject response = new JSONObject();
        try {
            response.put("id", id);
            response.put("ok", path != null);
            if (path != null) {
                JSONObject value = new JSONObject();
                value.put("api", 6);
                value.put("action", "pick-text");
                value.put("path", path);
                response.put("value", value);
            }
            reply.postMessage(response.toString());
        } catch (Exception ignored) { /* JS has its own bounded timeout. */ }
    }

    @Override public void onConfigurationChanged(Configuration config) {
        super.onConfigurationChanged(config);
        if (frame != null) frame.requestApplyInsets();
    }

    private void showConfirmUpdate() {
        // Update tile opens an explicit native confirmation; backend does not
        // accept concurrent or paused-state updates.
        if (destroyed || isFinishing() || isDestroyed()) return;
        if (updateConfirmation != null && updateConfirmation.isShowing()) return;
        updateConfirmation = new android.app.AlertDialog.Builder(this)
                .setTitle("Update Bindhosts rules?")
                .setMessage("Download configured sources and apply only after verification. An existing update cannot be restarted concurrently.")
                .setNegativeButton("Cancel", (dialog, which) ->
                        android.util.Log.i(P07_AUDIT_TAG, "QS_CONFIRM_CANCELLED"))
                .setPositiveButton("Update", (dialog, which) -> {
                    worker.execute(() -> {
                        String result;
                        try {
                            JSONObject receipt = RootRunner.control("update-start");
                            if (!receipt.getBoolean("accepted")) throw new IllegalStateException();
                            result = "Hosts update started. Open Rules to inspect progress.";
                        } catch (Exception denied) {
                            result = "Update refused or unverified. Check Rules and diagnostics.";
                        }
                        final String message = result;
                        runOnUiThread(() -> {
                            if (!destroyed && !isFinishing() && !isDestroyed())
                                android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show();
                        });
                    });
                }).create();
        updateConfirmation.setOnDismissListener(dialog -> updateConfirmation = null);
        updateConfirmation.show();
        android.util.Log.i(P07_AUDIT_TAG, "QS_CONFIRM_DIALOG_VISIBLE");
    }
    @Override public void onBackPressed() {
        if (web == null) { super.onBackPressed(); return; }
        // Forward Android Back through UX10's own managed-dialog/router handler.
        // The fixed expression contains no user-supplied JavaScript.
        web.evaluateJavascript("(window.__bhCompanionBack && window.__bhCompanionBack()) ? 'handled' : 'exit'",
                result -> {
                    if (!destroyed && "\"exit\"".equals(result)) finish();
                    else if (!destroyed && (result == null || "null".equals(result)) && pageLoadError) finish();
                });
    }
    @Override public void onDestroy() {
        destroyed = true;
        pendingUpdateConfirmation = false;
        updateConfirmationScheduled = false;
        if (updateConfirmation != null) {
            updateConfirmation.dismiss();
            updateConfirmation = null;
        }
        pickerId = null;
        pickerReply = null;
        if (worker != null) worker.shutdownNow();
        if (web != null) {
            web.stopLoading();
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
