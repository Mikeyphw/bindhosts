package com.mikeyphw.bindhosts;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** P03 status-only tile. Mutating toggle is intentionally deferred to P05. */
public final class ProtectionTileService extends TileService {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    @Override public void onStartListening() {
        super.onStartListening();
        render(Tile.STATE_UNAVAILABLE, "Checking…");
        executor.execute(() -> {
            int state = Tile.STATE_UNAVAILABLE;
            String subtitle = "Open app for diagnostics";
            try {
                JSONObject status = RootRunner.read("status");
                switch (status.getString("hosts")) {
                    case "ACTIVE": state = Tile.STATE_ACTIVE; subtitle = "Protection configured"; break;
                    case "PAUSED": state = Tile.STATE_INACTIVE; subtitle = "Paused"; break;
                    case "INACTIVE": state = Tile.STATE_INACTIVE; subtitle = "Not configured"; break;
                    case "DISABLED": subtitle = "Module disabled"; break;
                }
                if ("RUNNING".equals(status.getString("operation"))) subtitle = "Updating — open app";
            } catch (Exception ignored) { /* Never show stale success. */ }
            final int verified = state;
            final String label = subtitle;
            mainHandler.post(() -> {
                if (!executor.isShutdown()) render(verified, label);
            });
        });
    }
    private void render(int state, String subtitle) {
        Tile tile = getQsTile();
        if (tile == null) return;
        tile.setState(state);
        tile.setLabel("Bindhosts");
        if (Build.VERSION.SDK_INT >= 29) tile.setSubtitle(subtitle);
        tile.updateTile();
    }
    @Override public void onClick() {
        super.onClick();
        // No pause/resume until P05's write confirmation and read-back gates exist.
        Intent intent = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (Build.VERSION.SDK_INT >= 34) {
            PendingIntent pending = PendingIntent.getActivity(this, 0, intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            startActivityAndCollapse(pending);
        } else {
            startActivityAndCollapse(intent);
        }
    }
    @Override public void onDestroy() {
        mainHandler.removeCallbacksAndMessages(null);
        executor.shutdownNow();
        super.onDestroy();
    }
}
