package com.mikeyphw.bindhosts;

import android.content.Intent;
import android.app.AlertDialog;
import android.widget.Button;
import java.lang.reflect.Field;
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
import static androidx.test.espresso.assertion.ViewAssertions.matches;
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

    /** Read the real native AlertDialog, never Espresso's unfocused Activity root. */
    private static AlertDialog requireNativeUpdateConfirmation(
            android.app.Instrumentation instrumentation, MainActivity activity) throws Exception {
        Field field = MainActivity.class.getDeclaredField("updateConfirmation");
        field.setAccessible(true); // Our own app class; no Android hidden API.
        for (int n = 0; n < 50; n++) {
            AtomicReference<AlertDialog> current = new AtomicReference<>();
            instrumentation.runOnMainSync(() -> {
                try {
                    AlertDialog dialog = (AlertDialog) field.get(activity);
                    if (dialog != null && dialog.isShowing() && dialog.getWindow() != null &&
                            dialog.getButton(AlertDialog.BUTTON_NEGATIVE) != null) current.set(dialog);
                } catch (IllegalAccessException error) {
                    throw new AssertionError("Cannot inspect native dialog", error);
                }
            });
            if (current.get() != null) return current.get();
            Thread.sleep(100);
        }
        fail("Native QS update confirmation never became visible");
        return null;
    }

    private static boolean dialogHasText(View view, String expected) {
        if (view instanceof android.widget.TextView &&
                expected.equals(String.valueOf(((android.widget.TextView) view).getText())) &&
                view.isShown()) return true;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int n = 0; n < group.getChildCount(); n++) {
                if (dialogHasText(group.getChildAt(n), expected)) return true;
            }
        }
        return false;
    }

    @Test public void updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled() throws Exception {
        // HF04: HF02 and HF03 both passed the actual dialog + Cancel assertions,
        // but ActivityScenario.close() timed out waiting for DESTROYED (PAUSED in
        // HF02, RESUMED in HF03). Do not use ActivityScenario ownership for this
        // QS test. Real ActivityManager cold-start acceptance below in CI remains
        // independently mandatory, including the actual native Cancel click.
        android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Intent launch = new Intent(instrumentation.getTargetContext(), MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        MainActivity activity = (MainActivity) instrumentation.startActivitySync(launch);
        assertNotNull("Host Activity was not launched", activity);
        try {
            instrumentation.waitForIdleSync();
            instrumentation.runOnMainSync(() -> {
                assertFalse("Host Activity is finishing", activity.isFinishing());
                Intent qs = new Intent(activity, MainActivity.class)
                        .setAction(MainActivity.ACTION_CONFIRM_UPDATE);
                activity.onNewIntent(qs);
            });
            // Espresso's default RootViewPicker targeted the BASE_APPLICATION
            // background view, which correctly has no focus under AlertDialog.
            // Inspect the actual native AlertDialog window and press its real
            // negative button. The separate ADB cold-start test also performs
            // a physical UIAutomator-located Cancel tap on this emulator.
            AlertDialog confirmation = requireNativeUpdateConfirmation(instrumentation, activity);
            instrumentation.runOnMainSync(() -> {
                assertTrue("Native QS confirmation must be visible", confirmation.isShowing());
                assertTrue("Native title not shown in dialog window", dialogHasText(
                        confirmation.getWindow().getDecorView(), "Update Bindhosts rules?"));
                Button cancel = confirmation.getButton(AlertDialog.BUTTON_NEGATIVE);
                Button update = confirmation.getButton(AlertDialog.BUTTON_POSITIVE);
                assertNotNull("Cancel button missing", cancel);
                assertNotNull("Update button missing", update);
                assertTrue("Cancel button is not actually shown", cancel.isShown());
                assertEquals("Cancel", String.valueOf(cancel.getText()));
                assertEquals("Update", String.valueOf(update.getText()));
                assertTrue("Cancel click was refused", cancel.performClick());
            });
            instrumentation.waitForIdleSync();
            assertFalse("Cancel failed to dismiss real confirmation", confirmation.isShowing());
            instrumentation.runOnMainSync(() -> {
                assertFalse("QS action was not consumed",
                        MainActivity.ACTION_CONFIRM_UPDATE.equals(activity.getIntent().getAction()));
                assertFalse("Cancel unexpectedly finished the Activity", activity.isFinishing());
                assertNotNull("Cancel must leave the native WebView attached",
                        findWeb(activity.getWindow().getDecorView()));
            });
        } finally {
            // Best-effort explicit cleanup without AndroidX ActivityScenario.close,
            // which is the demonstrated failing operation in both hosted runs.
            instrumentation.runOnMainSync(() -> {
                if (!activity.isFinishing() && !activity.isDestroyed()) activity.finish();
            });
            instrumentation.waitForIdleSync();
        }
    }
}
