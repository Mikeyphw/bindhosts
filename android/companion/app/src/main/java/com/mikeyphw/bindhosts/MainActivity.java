package com.mikeyphw.bindhosts;

import android.app.Activity;
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

/** Read-only native bridge proof; the full UX10 bundle is not yet packaged. */
public final class MainActivity extends Activity {
    private static final String ORIGIN = "https://appassets.androidplatform.net";
    private ExecutorService worker;
    private WebView web;

    @Override public void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        worker = Executors.newSingleThreadExecutor();
        web = new WebView(this);
        setContentView(web);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setDomStorageEnabled(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return loader.shouldInterceptRequest(request.getUrl());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                return !request.isForMainFrame() || !ORIGIN.equals(uri.getScheme() + "://" + uri.getHost())
                        || !uri.getPath().startsWith("/assets/");
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
            if (data == null || data.length() > 512) return;
            final String id;
            final String op;
            try {
                JSONObject request = new JSONObject(data);
                if (request.length() != 2) return;
                id = request.getString("id");
                op = request.getString("op");
                if (!id.matches("bh[a-z0-9]{1,16}") || (!"hello".equals(op) && !"status".equals(op))) return;
            } catch (Exception ignored) { return; }
            worker.execute(() -> {
                JSONObject response = new JSONObject();
                try {
                    response.put("id", id);
                    response.put("ok", true);
                    response.put("value", RootRunner.read(op));
                } catch (Exception denied) {
                    try { response.put("id", id); response.put("ok", false); } catch (Exception ignored) { return; }
                }
                runOnUiThread(() -> replyProxy.postMessage(response.toString()));
            });
        });
        web.loadUrl(ORIGIN + "/assets/index.html");
    }
    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
    @Override public void onDestroy() {
        if (web != null) web.destroy();
        if (worker != null) worker.shutdownNow();
        super.onDestroy();
    }
}
