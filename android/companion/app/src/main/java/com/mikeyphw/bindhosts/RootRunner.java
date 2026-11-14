package com.mikeyphw.bindhosts;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/** Finite root reader; no user-provided shell strings. Never called on main thread. */
final class RootRunner {
    private static final String SCRIPT = "/data/adb/modules/bindhosts/companion_api.sh";
    static JSONObject read(String action) throws Exception {
        if (!"hello".equals(action) && !"status".equals(action)) throw new SecurityException("Unsupported operation");
        Process process = new ProcessBuilder("su", "-c", "/system/bin/sh " + SCRIPT + " " + action)
                .redirectErrorStream(false).start();
        try {
            if (!process.waitFor(8, TimeUnit.SECONDS)) throw new IllegalStateException("Root command timed out");
            if (process.exitValue() != 0) throw new IllegalStateException("Root or compatible module unavailable");
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (InputStream in = process.getInputStream()) {
                byte[] block = new byte[1024]; int count;
                while ((count = in.read(block)) != -1) {
                    if (buffer.size() + count > 8192) throw new IllegalStateException("Oversized module response");
                    buffer.write(block, 0, count);
                }
            }
            JSONObject body = new JSONObject(buffer.toString(StandardCharsets.UTF_8.name()));
            if (body.getInt("api") != 1) throw new IllegalStateException("Incompatible module API");
            if ("status".equals(action)) {
                switch (body.getString("hosts")) {
                    case "ACTIVE": case "PAUSED": case "INACTIVE": case "DISABLED": break;
                    default: throw new IllegalStateException("Unrecognized hosts state");
                }
                switch (body.getString("operation")) {
                    case "IDLE": case "RUNNING": case "DONE": case "FAILED": case "INTERRUPTED": break;
                    default: throw new IllegalStateException("Unrecognized operation state");
                }
            } else {
                if (!"bindhosts".equals(body.getString("module")) || body.getInt("versionCode") <= 0)
                    throw new IllegalStateException("Incompatible module handshake");
            }
            return body;
        } finally {
            process.destroyForcibly();
        }
    }
    private RootRunner() {}
}
