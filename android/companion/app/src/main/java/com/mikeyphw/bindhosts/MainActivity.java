package com.mikeyphw.bindhosts;

import android.app.Activity;
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
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private ExecutorService worker;
    private WebView web;

    @Override public void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        worker = Executors.newSingleThreadExecutor();
        web = new WebView(this);
        // An out-of-WebView disclosure cannot be hidden by a bundled page.
        LinearLayout frame = new LinearLayout(this);
        frame.setOrientation(LinearLayout.VERTICAL);
        frame.setBackgroundColor(Color.rgb(18, 20, 24));
        TextView disclaimer = new TextView(this);
        disclaimer.setText("UX10 shared UI · VERIFIED HOSTS CONTROLS · bounded Rules, Sources and TrackerGuard operations · backups/HTTPS disabled");
        disclaimer.setTextColor(Color.WHITE);
        disclaimer.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        disclaimer.setPadding(18, 12, 18, 12);
        disclaimer.setBackgroundColor(Color.rgb(47, 52, 64));
        frame.addView(disclaimer, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        frame.addView(web, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(frame);
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
            try {
                JSONObject request = new JSONObject(data);
                id = request.getString("id");
                op = request.getString("op");
                management = RootRunner.isManagementOperation(op) || "read-page".equals(op);
                if (!id.matches("bh[a-z0-9]{1,16}")) return;
                if (management) {
                    if (request.length() != 3 || !request.has("arg")) return;
                    argument = request.getString("arg");
                    if (!("read-page".equals(op) ? RootRunner.validPageArgument(argument) : RootRunner.validManagementArgument(argument))) return;
                } else {
                    if (request.length() != 2 || (!"hello".equals(op) && !"status".equals(op) &&
                            !"pause".equals(op) && !"resume".equals(op) &&
                            !"update-start".equals(op) && !"update-status".equals(op) && !"update-events".equals(op))) return;
                    argument = "";
                }
            } catch (Exception ignored) { return; }
            worker.execute(() -> {
                JSONObject response = new JSONObject();
                try {
                    response.put("id", id);
                    response.put("ok", true);
                    response.put("value", "read-page".equals(op) ? RootRunner.page(argument) :
                            management ? RootRunner.manage(op, argument) :
                            (("hello".equals(op) || "status".equals(op))
                            ? RootRunner.read(op) : RootRunner.control(op)));
                } catch (Exception denied) {
                    try { response.put("id", id); response.put("ok", false); } catch (Exception ignored) { return; }
                }
                runOnUiThread(() -> replyProxy.postMessage(response.toString()));
            });
        });
        web.loadUrl(ORIGIN + "/assets/ux10/index.html");
        if (ACTION_CONFIRM_UPDATE.equals(getIntent().getAction())) showConfirmUpdate();
    }
    @Override protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (ACTION_CONFIRM_UPDATE.equals(intent.getAction())) showConfirmUpdate();
    }
    private void showConfirmUpdate() {
        // Update tile opens an explicit native confirmation; backend does not
        // accept concurrent or paused-state updates.
        new android.app.AlertDialog.Builder(this)
                .setTitle("Update Bindhosts rules?")
                .setMessage("Download configured sources and apply only after verification. An existing update cannot be restarted concurrently.")
                .setNegativeButton("Cancel", (dialog, which) -> {})
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
                            if (!isFinishing() && !isDestroyed())
                                android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show();
                        });
                    });
                }).show();
    }
    @Override public void onBackPressed() {
        if (web == null) { super.onBackPressed(); return; }
        // Forward Android Back through UX10's own managed-dialog/router handler.
        // The fixed expression contains no user-supplied JavaScript.
        web.evaluateJavascript("(window.__bhCompanionBack && window.__bhCompanionBack()) ? 'handled' : 'exit'",
                result -> {
                    if ("\"exit\"".equals(result)) finish();
                });
    }
    @Override public void onDestroy() {
        if (web != null) web.destroy();
        if (worker != null) worker.shutdownNow();
        super.onDestroy();
    }
}
