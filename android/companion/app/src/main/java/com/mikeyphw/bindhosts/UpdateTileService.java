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

/** Secondary tile: opens a native confirmation; never auto-updates on tap. */
public final class UpdateTileService extends TileService {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile boolean destroyed = false;

    @Override public void onStartListening() {
        super.onStartListening();
        render(Tile.STATE_UNAVAILABLE, "Checking update…");
        executor.execute(() -> {
            int state = Tile.STATE_UNAVAILABLE;
            String subtitle = "Open app for details";
            try {
                JSONObject hosts = RootRunner.read("status");
                JSONObject update = RootRunner.control("update-status");
                if ("RUNNING".equals(update.getString("operation"))) {
                    subtitle = "Update running";
                } else if ("INTERRUPTED".equals(update.getString("operation"))) {
                    subtitle = "Inspect interrupted update";
                } else if ("ACTIVE".equals(hosts.getString("hosts")) || "INACTIVE".equals(hosts.getString("hosts"))) {
                    state = Tile.STATE_INACTIVE;
                    subtitle = "Tap to review update";
                } else {
                    subtitle = "Resume blocking first";
                }
            } catch (Exception ignored) { subtitle = "Status unavailable"; }
            int value = state;
            String text = subtitle;
            main.post(() -> { if (!destroyed) render(value, text); });
        });
    }
    @Override public void onClick() {
        super.onClick();
        Intent intent = new Intent(this, MainActivity.class)
                .setAction(MainActivity.ACTION_CONFIRM_UPDATE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (Build.VERSION.SDK_INT >= 34) {
            PendingIntent pending = PendingIntent.getActivity(this, 101, intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            startActivityAndCollapse(pending);
        } else {
            startActivityAndCollapse(intent);
        }
    }
    private void render(int state, String subtitle) {
        Tile tile = getQsTile();
        if (tile == null) return;
        tile.setState(state);
        tile.setLabel("Update hosts");
        if (Build.VERSION.SDK_INT >= 29) tile.setSubtitle(subtitle);
        tile.updateTile();
    }
    @Override public void onDestroy() {
        destroyed = true;
        main.removeCallbacksAndMessages(null);
        executor.shutdownNow();
        super.onDestroy();
    }
}
