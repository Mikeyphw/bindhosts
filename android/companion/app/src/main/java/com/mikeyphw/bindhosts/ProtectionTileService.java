package com.mikeyphw.bindhosts;

import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import android.widget.Toast;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** P05: one-tap verified hosts pause/resume. Other states never perform writes. */
public final class ProtectionTileService extends TileService {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean changing = new AtomicBoolean(false);
    private volatile boolean destroyed = false;
    private volatile long lastToggleAt = 0;

    @Override public void onStartListening() {
        super.onStartListening();
        render(Tile.STATE_UNAVAILABLE, "Checking…");
        executor.execute(this::refresh);
    }
    private void refresh() {
        try {
            JSONObject status = RootRunner.read("status");
            String state = status.getString("hosts");
            if ("RUNNING".equals(status.getString("operation"))) {
                dispatch(Tile.STATE_UNAVAILABLE, "Update in progress");
            } else {
                switch (state) {
                    case "ACTIVE": dispatch(Tile.STATE_ACTIVE, "Tap to pause"); break;
                    case "PAUSED": dispatch(Tile.STATE_INACTIVE, "Tap to resume"); break;
                    case "INACTIVE": dispatch(Tile.STATE_UNAVAILABLE, "Update hosts first"); break;
                    default: dispatch(Tile.STATE_UNAVAILABLE, "Module disabled");
                }
            }
        } catch (Exception error) {
            dispatch(Tile.STATE_UNAVAILABLE, "Status unavailable");
        }
    }
    @Override public void onClick() {
        super.onClick();
        long now = android.os.SystemClock.elapsedRealtime();
        if (now - lastToggleAt < 1400L || !changing.compareAndSet(false, true) || executor.isShutdown()) return;
        lastToggleAt = now;
        render(Tile.STATE_UNAVAILABLE, "Verifying…");
        executor.execute(() -> {
            String result = "Unable to verify change";
            try {
                JSONObject before = RootRunner.read("status");
                if ("RUNNING".equals(before.getString("operation")) || "INTERRUPTED".equals(before.getString("operation")))
                    throw new IllegalStateException("Update busy");
                String action;
                switch (before.getString("hosts")) {
                    case "ACTIVE": action = "pause"; break;
                    case "PAUSED": action = "resume"; break;
                    default: throw new IllegalStateException("No safe toggle available");
                }
                JSONObject changed = RootRunner.control(action);
                JSONObject after = RootRunner.read("status");
                String expected = action.equals("pause") ? "PAUSED" : "ACTIVE";
                if (!changed.getBoolean("verified") || !expected.equals(changed.getString("hosts")) || !expected.equals(after.getString("hosts")))
                    throw new IllegalStateException("Post-action read-back mismatch");
                result = action.equals("pause") ? "Blocking paused" : "Blocking resumed";
            } catch (Exception error) {
                result = "Protection unchanged or unverified — open app";
            } finally {
                changing.set(false);
                refresh();
                final String message = result;
                mainHandler.post(() -> { if (!destroyed) Toast.makeText(this, message, Toast.LENGTH_SHORT).show(); });
            }
        });
    }
    private void dispatch(int state, String label) {
        mainHandler.post(() -> { if (!destroyed) render(state, label); });
    }
    private void render(int state, String subtitle) {
        Tile tile = getQsTile();
        if (tile == null) return;
        tile.setState(state);
        tile.setLabel("Bindhosts");
        if (Build.VERSION.SDK_INT >= 29) tile.setSubtitle(subtitle);
        tile.updateTile();
    }
    @Override public void onDestroy() {
        destroyed = true;
        mainHandler.removeCallbacksAndMessages(null);
        executor.shutdownNow();
        super.onDestroy();
    }
}
