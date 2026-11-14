package com.mikeyphw.bindhosts;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static androidx.test.espresso.Espresso.onView;
import static androidx.test.espresso.action.ViewActions.click;
import static androidx.test.espresso.assertion.ViewAssertions.matches;
import static androidx.test.espresso.matcher.ViewMatchers.isDisplayed;
import static androidx.test.espresso.matcher.ViewMatchers.withText;
import static org.junit.Assert.*;

/** P07 disposable API36 hosted emulator only. Never invokes privileged writes. */
@RunWith(AndroidJUnit4.class)
public final class P07HostedUiTest {
    private static WebView findWeb(View view) {
        if (view instanceof WebView) return (WebView) view;
        if (view instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) view;
            for (int n = 0; n < g.getChildCount(); n++) {
                WebView found = findWeb(g.getChildAt(n));
                if (found != null) return found;
            }
        }
        return null;
    }

    private static String js(WebView web, String script) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> output = new AtomicReference<>("");
        InstrumentationRegistry.getInstrumentation().runOnMainSync(() ->
                web.evaluateJavascript(script, result -> {
                    output.set(result);
                    done.countDown();
                }));
        assertTrue("WebView JS callback did not complete", done.await(15, TimeUnit.SECONDS));
        return output.get();
    }

    @Test public void actualUx10BundleLoadsFromLocalAssetOrigin() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            AtomicReference<WebView> result = new AtomicReference<>();
            scenario.onActivity(activity -> {
                WebView web = findWeb(activity.getWindow().getDecorView());
                assertNotNull("Native Activity did not attach its WebView", web);
                result.set(web);
                assertFalse("Unrestricted file reads", web.getSettings().getAllowFileAccess());
                assertFalse("Content URI reads must use the native picker", web.getSettings().getAllowContentAccess());
                assertFalse("WebView window popups must stay disabled", web.getSettings().getJavaScriptCanOpenWindowsAutomatically());
            });
            WebView web = result.get();
            boolean ready = false;
            for (int attempt = 0; attempt < 35; attempt++) {
                if ("true".equals(js(web, "(() => document.readyState === 'complete' && " +
                        "location.origin === 'https://appassets.androidplatform.net' && " +
                        "location.pathname === '/assets/ux10/index.html' && " +
                        "!!document.querySelector('#content-container') && " +
                        "document.querySelectorAll('.bottom-bar-item').length >= 3)()"))) {
                    ready = true;
                    break;
                }
                Thread.sleep(500);
            }
            assertTrue("Compiled UX10 bundle did not mount inside its local origin", ready);
        }
    }

    @Test public void releaseManifestAndBridgeRefuseArbitraryCommands() throws Exception {
        PackageInfo info = InstrumentationRegistry.getInstrumentation().getTargetContext()
                .getPackageManager().getPackageInfo("com.mikeyphw.bindhosts", PackageManager.GET_PERMISSIONS);
        if (info.requestedPermissions != null) {
            assertFalse("Native companion unexpectedly requests network permission",
                    Arrays.asList(info.requestedPermissions).contains("android.permission.INTERNET"));
        }
        assertFalse(RootRunner.isManagementOperation("shell"));
        assertFalse(RootRunner.isManagementOperation("exec"));
        assertFalse(RootRunner.isMoreOperation("sh"));
        assertFalse(RootRunner.validManagementArgument("pause; rm -rf /"));
        assertFalse(RootRunner.validMoreArgument("../../secret"));
        assertFalse(RootRunner.validPageArgument("exec|all|0|none"));
    }

    @Test public void updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled() throws Exception {
        Intent i = new Intent(InstrumentationRegistry.getInstrumentation().getTargetContext(), MainActivity.class);
        i.setAction(MainActivity.ACTION_CONFIRM_UPDATE);
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(i)) {
            // Cold-start QS ACTION_CONFIRM_UPDATE must reach RESUMED before
            // showing the native confirmation; the previous onCreate modal
            // stalled ActivityScenario at PRE_ON_CREATE in hosted API36.
            scenario.onActivity(activity -> {
                assertFalse("Confirmation action must be consumed once", 
                        MainActivity.ACTION_CONFIRM_UPDATE.equals(activity.getIntent().getAction()));
            });
            onView(withText("Update Bindhosts rules?")).check(matches(isDisplayed()));
            // Never tap the positive action on a hosted emulator or a real device.
            onView(withText("Cancel")).perform(click());
            AtomicReference<WebView> current = new AtomicReference<>();
            scenario.onActivity(activity -> {
                assertFalse(activity.isFinishing());
                current.set(findWeb(activity.getWindow().getDecorView()));
            });
            assertNotNull("Cancelling must leave the companion running", current.get());
        }
    }
}
