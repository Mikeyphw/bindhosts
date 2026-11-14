package com.mikeyphw.bindhosts;

import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.util.UUID;

/** P06: copy one explicitly selected SAF text document into app-owned external cache.
 * Rooted import still runs only through the existing validated UX02 backend.
 * No filesystem path supplied by the provider is trusted or passed to root. */
final class NativeImportPicker {
    private static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final int MAX_FILES = 32;
    private static final long STALE_MS = 60L * 60L * 1000L;

    static String copy(Context context, Uri uri) throws IOException {
        if (uri == null || !"content".equals(uri.getScheme()))
            throw new IOException("Unsupported document URI");
        File cache = context.getExternalCacheDir();
        if (cache == null || !cache.isDirectory() || Files.isSymbolicLink(cache.toPath()))
            throw new IOException("Private external cache unavailable");
        File directory = new File(cache, "imports");
        if (!directory.isDirectory() && !directory.mkdir())
            throw new IOException("Cannot create private import staging");
        if (Files.isSymbolicLink(directory.toPath()))
            throw new IOException("Unsafe import directory");
        String canonical = directory.getCanonicalPath();
        String physicalCache = cache.getCanonicalPath();
        // Canonical paths may resolve the emulated-storage mount, while the
        // absolute path is what the established rooted UX02 contract accepts.
        if (!canonical.equals(physicalCache + File.separator + "imports") ||
                !directory.getAbsolutePath().equals(
                    "/storage/emulated/0/Android/data/com.mikeyphw.bindhosts/cache/imports"))
            throw new IOException("Unexpected Android storage mount");
        pruneOld(directory);
        File[] existing = directory.listFiles();
        if (existing == null || existing.length >= MAX_FILES)
            throw new IOException("Import staging is full");
        String displayName = queryName(context, uri);
        if (displayName == null || !displayName.matches("[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\\.txt")
                || displayName.contains(".."))
            throw new IOException("Choose a plain .txt hosts file with a simple name");
        String token = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        File target = new File(directory, "bh-pick-" + token + "-" + displayName);
        if (!target.getCanonicalPath().startsWith(canonical + File.separator) ||
                Files.isSymbolicLink(target.toPath()) || !target.createNewFile())
            throw new IOException("Unsafe or duplicate import file");
        boolean saved = false;
        try (InputStream in = context.getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(target)) {
            if (in == null) throw new IOException("Document unavailable");
            byte[] buffer = new byte[4096];
            int total = 0, n;
            while ((n = in.read(buffer)) != -1) {
                if (n == 0) continue;
                total += n;
                if (total > MAX_BYTES) throw new IOException("Import exceeds 2 MiB");
                for (int i = 0; i < n; i++) {
                    int value = buffer[i] & 0xff;
                    // UX02 safe editor accepts LF-separated, printable ASCII hosts entries.
                    // Reject NUL, CRLF and binary rather than silently normalizing data.
                    if (value != 10 && (value < 32 || value > 126))
                        throw new IOException("Document contains unsupported characters");
                }
                out.write(buffer, 0, n);
            }
            if (total == 0) throw new IOException("Empty hosts file");
            out.getFD().sync();
            saved = true;
        } finally {
            if (!saved) target.delete();
        }
        return target.getAbsolutePath();
    }

    private static String queryName(Context context, Uri uri) throws IOException {
        try (Cursor cursor = context.getContentResolver().query(uri,
                new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor == null || !cursor.moveToFirst())
                throw new IOException("Document name unavailable");
            int column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
            if (column < 0 || cursor.isNull(column))
                throw new IOException("Document name unavailable");
            return cursor.getString(column);
        } catch (SecurityException denied) {
            throw new IOException("Document access denied", denied);
        }
    }

    private static void pruneOld(File directory) {
        File[] files = directory.listFiles();
        if (files == null) return;
        long cutoff = System.currentTimeMillis() - STALE_MS;
        for (File file : files) {
            if (file.getName().matches("bh-pick-[0-9a-f]{12}-[A-Za-z0-9_.-]+\\.txt") &&
                    file.isFile() && !Files.isSymbolicLink(file.toPath()) && file.lastModified() < cutoff)
                file.delete();
        }
    }
    private NativeImportPicker() {}
}
