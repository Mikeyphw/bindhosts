package com.mikeyphw.trackerguard.ifwlab;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/** Dedicated test receiver: no trackers, no network, no SDKs. */
public final class ProbeReceiver extends BroadcastReceiver {
    public static final String ACTION = "com.mikeyphw.trackerguard.ifwlab.PROBE";
    public static final String RECORD_FILE = "received-events.log";
    public static final int ORDERED_RESULT = 243;

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!ACTION.equals(intent.getAction())) {
            return;
        }
        String token = intent.getStringExtra("token");
        if (token == null || !token.matches("[A-Za-z0-9_-]{1,80}")) {
            Log.w("TG_IFW_LAB", "REJECTED_INVALID_TOKEN");
            return;
        }
        File target = new File(context.getFilesDir(), RECORD_FILE);
        // Bound disk use: exported receivers can be called by other apps.
        if (target.length() >= 65536) {
            Log.w("TG_IFW_LAB", "RECORD_LIMIT_REACHED");
            return;
        }
        try (FileOutputStream out = new FileOutputStream(target, true)) {
            out.write((token + "\n").getBytes(StandardCharsets.UTF_8));
            out.flush();
            Log.i("TG_IFW_LAB", "TG_IFW_LAB_RECEIVED " + token);
            if (isOrderedBroadcast()) {
                setResultCode(ORDERED_RESULT);
            }
        } catch (IOException e) {
            Log.e("TG_IFW_LAB", "Could not persist probe delivery", e);
        }
    }
}
