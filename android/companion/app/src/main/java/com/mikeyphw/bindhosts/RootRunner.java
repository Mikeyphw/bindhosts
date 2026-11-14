package com.mikeyphw.bindhosts;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/** Fixed-verb root broker. No caller-controlled command, path or shell arguments. */
final class RootRunner {
    private static final String READ_SCRIPT = "/data/adb/modules/bindhosts/companion_api.sh";
    private static final String CONTROL_SCRIPT = "/data/adb/modules/bindhosts/companion_control_v2.sh";
    private static final String MANAGE_SCRIPT = "/data/adb/modules/bindhosts/companion_manage_v3.sh";
    private static final String PAGE_SCRIPT = "/data/adb/modules/bindhosts/companion_read_v4.sh";

    static JSONObject read(String action) throws Exception {
        if (!"hello".equals(action) && !"status".equals(action))
            throw new SecurityException("Unsupported read operation");
        JSONObject body = call(READ_SCRIPT, action);
        if (body.getInt("api") != 1) throw new IllegalStateException("Incompatible read API");
        if ("status".equals(action)) {
            state(body.getString("hosts"));
            operation(body.getString("operation"));
        } else {
            if (!"bindhosts".equals(body.getString("module")) || body.getInt("versionCode") <= 0)
                throw new IllegalStateException("Invalid module handshake");
        }
        return body;
    }

    static JSONObject control(String action) throws Exception {
        switch (action) {
            case "pause": case "resume": case "update-start": case "update-status": case "update-events": break;
            default: throw new SecurityException("Unsupported control operation");
        }
        JSONObject body = call(CONTROL_SCRIPT, action);
        if (body.getInt("api") != 2 || !action.equals(body.getString("action")))
            throw new IllegalStateException("Incompatible control API");
        switch (action) {
            case "pause": case "resume":
                if (!body.getBoolean("verified") || !body.getString("hosts").equals(action.equals("pause") ? "PAUSED" : "ACTIVE"))
                    throw new IllegalStateException("Hosts read-back failed");
                break;
            case "update-start":
                if (!body.getBoolean("accepted") || !("RUNNING".equals(body.getString("operation")) || "DONE".equals(body.getString("operation"))))
                    throw new IllegalStateException("Journaled update launch failed");
                break;
            case "update-status":
                operation(body.getString("operation"));
                String step = body.getString("step");
                String receipt = body.getString("receipt");
                if (!step.matches("NONE|PREPARING|DOWNLOADING|PARSED|SKIPPED_DUPLICATE_URL|DEDUPLICATING|ALLOWLIST|GENERATING|COMMITTING|DONE|UNCHANGED|FAILED|STATS") ||
                        !receipt.matches("NONE|PASS|FAIL") || ("DONE".equals(body.getString("operation")) && !"PASS".equals(receipt)))
                    throw new IllegalStateException("Invalid operation receipt");
                break;
            case "update-events":
                String encoded = body.getString("encoded");
                if (encoded.length() > 6500 || !encoded.matches("(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"))
                    throw new IllegalStateException("Invalid event encoding");
                break;
        }
        return body;
    }

    static boolean isManagementOperation(String op) {
        if (op == null) return false;
        switch (op) {
            case "config-read": case "config-list": case "config-write":
            case "catalog": case "tracker": case "packages": return true;
            default: return false;
        }
    }

    static boolean validManagementArgument(String arg) {
        return arg != null && arg.length() >= 1 && arg.length() <= 13000 &&
                arg.matches("[A-Za-z0-9_.+\\/=,|\\-]+") && !arg.contains("..");
    }

    static JSONObject manage(String op, String arg) throws Exception {
        if (!isManagementOperation(op) || !validManagementArgument(arg))
            throw new SecurityException("Invalid management operation or argument");
        // Argument is base64-encoded *before* reaching su -c; shell metacharacters
        // cannot be inserted into the command. The rooted v3 API validates tokens.
        String encodedArgument = android.util.Base64.encodeToString(
                arg.getBytes(StandardCharsets.US_ASCII), android.util.Base64.NO_WRAP);
        JSONObject result = call(MANAGE_SCRIPT, op + " " + encodedArgument);
        if (result.length() != 3 || result.getInt("api") != 3 || !op.equals(result.getString("action")))
            throw new IllegalStateException("Incompatible v3 backend reply");
        String output = result.getString("encoded");
        if (output.length() > 6500 || !output.matches("(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"))
            throw new IllegalStateException("Unsafe v3 response");
        return result;
    }

    static boolean validPageArgument(String arg) {
        return arg != null && arg.length() >= 12 && arg.length() <= 480 &&
                arg.matches("(?:config-read|config-list|catalog|tracker|packages)\\|[A-Za-z0-9_.~-]{1,110}\\|[0-9]{1,6}\\|(?:none|[0-9a-f]{64})")
                && !arg.contains("..");
    }

    static JSONObject page(String arg) throws Exception {
        if (!validPageArgument(arg)) throw new SecurityException("Unsupported paged read request");
        String encodedArg = android.util.Base64.encodeToString(
                arg.getBytes(StandardCharsets.US_ASCII), android.util.Base64.NO_WRAP);
        JSONObject body = call(PAGE_SCRIPT, encodedArg);
        if (body.length() != 9 || body.getInt("api") != 4 || !"read-page".equals(body.getString("action")))
            throw new IllegalStateException("Incompatible paged-read API");
        String[] parts = arg.split("\\|", -1);
        if (!parts[0].equals(body.getString("source")) || !parts[1].equals(body.getString("selector")) ||
                Long.parseLong(parts[2]) != body.getLong("offset"))
            throw new IllegalStateException("Paged read identity mismatch");
        long size = body.getLong("size"), offset = body.getLong("offset");
        if (size < 0 || size > 262144 || offset < 0 || offset > size)
            throw new IllegalStateException("Invalid paged-read bounds");
        String hash = body.getString("sha256");
        if (!hash.matches("[0-9a-f]{64}") || (!"none".equals(parts[3]) && !hash.equals(parts[3])))
            throw new IllegalStateException("Paged read fingerprint mismatch");
        String encoded = body.getString("encoded");
        if (encoded.length() > 4096 || !encoded.matches("(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"))
            throw new IllegalStateException("Invalid paged-read base64");
        int count = android.util.Base64.decode(encoded, android.util.Base64.DEFAULT).length;
        if (count > 3072 || count != Math.min(3072L, size-offset))
            throw new IllegalStateException("Paged-read byte count mismatch");
        if (body.isNull("next")) {
            if (offset+count != size) throw new IllegalStateException("Incomplete final page");
        } else if (body.getLong("next") != offset+count || offset+count >= size) {
            throw new IllegalStateException("Invalid next page");
        }
        return body;
    }

    private static void state(String value) {
        switch (value) {
            case "ACTIVE": case "PAUSED": case "INACTIVE": case "DISABLED": return;
            default: throw new IllegalStateException("Unrecognized hosts state");
        }
    }
    private static void operation(String value) {
        switch (value) {
            case "IDLE": case "RUNNING": case "DONE": case "FAILED": case "INTERRUPTED": return;
            default: throw new IllegalStateException("Unrecognized update state");
        }
    }

    private static JSONObject call(String script, String verb) throws Exception {
        // Both components are private constants or a finite allowlisted token.
        Process process = new ProcessBuilder("su", "-c", "/system/bin/sh " + script + " " + verb)
                .redirectErrorStream(false).start();
        try {
            if (!process.waitFor(12, TimeUnit.SECONDS)) throw new IllegalStateException("Root command timed out");
            if (process.exitValue() != 0) throw new IllegalStateException("Root, module or safe operation unavailable");
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (InputStream in = process.getInputStream()) {
                byte[] block = new byte[1024]; int size;
                while ((size = in.read(block)) != -1) {
                    if (buffer.size() + size > 8192) throw new IllegalStateException("Oversized control response");
                    buffer.write(block, 0, size);
                }
            }
            return new JSONObject(buffer.toString(StandardCharsets.UTF_8.name()));
        } finally {
            process.destroyForcibly();
        }
    }
    private RootRunner() {}
}
