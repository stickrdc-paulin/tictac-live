package cd.tictachebdo.live;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Compare versionName locale à downloads/index.json distant.
 * Même applicationId → l’utilisateur installe le nouvel APK par-dessus.
 */
final class UpdateChecker {
    private static final String[] INDEX_URLS = {
            // Catalogue JSON seulement — APK sur GitHub Releases, pas Verpex.
            "https://raw.githubusercontent.com/stickrdc-paulin/tictac-live/main/downloads/index.json",
            "https://tictachebdo.cd/wp-content/uploads/tictac-live/index.json"
    };

    private UpdateChecker() {
    }

    static void checkAsync(Activity activity) {
        new Thread(() -> {
            try {
                String local = localVersion(activity);
                JSONObject androidMeta = fetchAndroidMeta();
                if (androidMeta == null) {
                    return;
                }
                String remote = androidMeta.optString("version", "").trim();
                if (remote.isEmpty() || !isNewer(remote, local)) {
                    return;
                }
                String download = androidMeta.optString("download", "").trim();
                if (download.isEmpty()) {
                    download = androidMeta.optString("github_release", "").trim();
                }
                if (download.isEmpty()) {
                    return;
                }
                final String url = download;
                final String ver = remote;
                activity.runOnUiThread(() -> {
                    Toast.makeText(
                            activity,
                            "Nouvelle version " + ver + " disponible — téléchargement…",
                            Toast.LENGTH_LONG
                    ).show();
                    try {
                        activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (Exception ignored) {
                    }
                });
            } catch (Exception ignored) {
            }
        }, "tictac-update").start();
    }

    private static String localVersion(Activity activity) {
        try {
            PackageInfo pi = activity.getPackageManager()
                    .getPackageInfo(activity.getPackageName(), 0);
            return pi.versionName != null ? pi.versionName : "0.0.0";
        } catch (PackageManager.NameNotFoundException e) {
            return "0.0.0";
        }
    }

    private static JSONObject fetchAndroidMeta() {
        for (String indexUrl : INDEX_URLS) {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(indexUrl).openConnection();
                conn.setConnectTimeout(4000);
                conn.setReadTimeout(4000);
                conn.setRequestProperty("Accept", "application/json");
                if (conn.getResponseCode() != 200) {
                    continue;
                }
                StringBuilder sb = new StringBuilder();
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        sb.append(line);
                    }
                }
                JSONObject root = new JSONObject(sb.toString());
                JSONObject android = root.optJSONObject("android");
                if (android != null && android.has("version")) {
                    return android;
                }
            } catch (Exception ignored) {
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }
        return null;
    }

    static boolean isNewer(String remote, String local) {
        return compareSemver(remote, local) > 0;
    }

    private static int compareSemver(String a, String b) {
        int[] aa = parse(a);
        int[] bb = parse(b);
        for (int i = 0; i < 3; i++) {
            if (aa[i] != bb[i]) {
                return Integer.compare(aa[i], bb[i]);
            }
        }
        return 0;
    }

    private static int[] parse(String v) {
        String[] parts = (v == null ? "" : v.trim()).split("\\.");
        int[] out = new int[3];
        for (int i = 0; i < 3; i++) {
            try {
                out[i] = i < parts.length ? Integer.parseInt(parts[i].replaceAll("[^0-9].*$", "")) : 0;
            } catch (NumberFormatException e) {
                out[i] = 0;
            }
        }
        return out;
    }
}
