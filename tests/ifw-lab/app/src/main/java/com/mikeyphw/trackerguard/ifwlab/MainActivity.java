package com.mikeyphw.trackerguard.ifwlab;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;

/** Opens the test app to clear package-stopped state; no background service or network. */
public final class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TextView info = new TextView(this);
        info.setPadding(40, 56, 40, 40);
        info.setTextSize(17);
        info.setText("TrackerGuard — IFW Receiver Lab\n\n"
                + "This APK contains one exported test broadcast receiver. "
                + "It has no network permission, tracking SDKs or background service.\n\n"
                + "Use the supplied Termux test script to measure delivery "
                + "before blocking, during blocking, and after rollback.\n\n"
                + "Recorded probe deliveries: " + countRecords());
        setContentView(info);
    }

    private int countRecords() {
        File log = new File(getFilesDir(), ProbeReceiver.RECORD_FILE);
        if (!log.isFile()) {
            return 0;
        }
        int count = 0;
        try (BufferedReader reader = new BufferedReader(new FileReader(log))) {
            while (reader.readLine() != null) {
                count++;
            }
        } catch (IOException ignored) {
            return -1;
        }
        return count;
    }
}
