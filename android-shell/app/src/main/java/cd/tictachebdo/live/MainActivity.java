package cd.tictachebdo.live;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.os.Bundle;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.google.android.material.tabs.TabLayout;

public class MainActivity extends AppCompatActivity {
    private static final int REQ_MIC = 42;

    private WebView web;
    private LinearLayout listenPanel;
    private TextView listenStatus;
    private Button btnListen;
    private MediaPlayer player;
    private boolean playing;
    private PermissionRequest pendingMediaRequest;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        web = findViewById(R.id.web);
        listenPanel = findViewById(R.id.listenPanel);
        listenStatus = findViewById(R.id.listenStatus);
        btnListen = findViewById(R.id.btnListen);
        TabLayout tabs = findViewById(R.id.tabs);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> {
                    boolean needsAudio = false;
                    for (String r : request.getResources()) {
                        if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) {
                            needsAudio = true;
                            break;
                        }
                    }
                    if (!needsAudio) {
                        request.grant(request.getResources());
                        return;
                    }
                    if (ContextCompat.checkSelfPermission(MainActivity.this, Manifest.permission.RECORD_AUDIO)
                            == PackageManager.PERMISSION_GRANTED) {
                        request.grant(request.getResources());
                    } else {
                        pendingMediaRequest = request;
                        ActivityCompat.requestPermissions(
                                MainActivity.this,
                                new String[]{Manifest.permission.RECORD_AUDIO},
                                REQ_MIC
                        );
                    }
                });
            }
        });

        tabs.addTab(tabs.newTab().setText(R.string.tab_listen));
        tabs.addTab(tabs.newTab().setText(R.string.tab_report));
        tabs.addOnTabSelectedListener(new TabLayout.OnTabSelectedListener() {
            @Override
            public void onTabSelected(TabLayout.Tab tab) {
                if (tab.getPosition() == 0) {
                    showListen();
                } else {
                    showReporter();
                }
            }

            @Override
            public void onTabUnselected(TabLayout.Tab tab) {
            }

            @Override
            public void onTabReselected(TabLayout.Tab tab) {
            }
        });

        btnListen.setOnClickListener(v -> toggleListen());
        showListen();
        refreshStatus();
    }

    private void showListen() {
        stopPlayer();
        web.setVisibility(android.view.View.GONE);
        listenPanel.setVisibility(android.view.View.VISIBLE);
        refreshStatus();
    }

    private void showReporter() {
        stopPlayer();
        listenPanel.setVisibility(android.view.View.GONE);
        web.setVisibility(android.view.View.VISIBLE);
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
        }
        web.loadUrl(getString(R.string.reporter_url));
    }

    private void refreshStatus() {
        listenStatus.setText(playing ? "Lecture en cours" : "Prêt — flux TIC-TAC Radio");
        btnListen.setText(playing ? "Arrêter" : "Écouter en direct");
    }

    private void toggleListen() {
        if (playing) {
            stopPlayer();
            refreshStatus();
            return;
        }
        try {
            stopPlayer();
            player = new MediaPlayer();
            player.setAudioAttributes(
                    new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                            .build()
            );
            String url = getString(R.string.listen_url) + "?t=" + System.currentTimeMillis();
            player.setDataSource(url);
            player.setOnPreparedListener(mp -> {
                mp.start();
                playing = true;
                refreshStatus();
            });
            player.setOnErrorListener((mp, what, extra) -> {
                playing = false;
                listenStatus.setText("Flux indisponible (hors antenne ?)");
                btnListen.setText("Réessayer");
                return true;
            });
            player.prepareAsync();
            listenStatus.setText("Connexion…");
        } catch (Exception e) {
            listenStatus.setText("Erreur de lecture");
            Toast.makeText(this, e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private void stopPlayer() {
        playing = false;
        if (player != null) {
            try {
                player.stop();
            } catch (Exception ignored) {
            }
            try {
                player.release();
            } catch (Exception ignored) {
            }
            player = null;
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_MIC) return;
        boolean ok = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (pendingMediaRequest != null) {
            if (ok) {
                pendingMediaRequest.grant(pendingMediaRequest.getResources());
            } else {
                pendingMediaRequest.deny();
                Toast.makeText(this, R.string.mic_rationale, Toast.LENGTH_LONG).show();
            }
            pendingMediaRequest = null;
        } else if (!ok) {
            Toast.makeText(this, R.string.mic_rationale, Toast.LENGTH_LONG).show();
        }
    }

    @Override
    public void onBackPressed() {
        if (web.getVisibility() == android.view.View.VISIBLE && web.canGoBack()) {
            web.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        stopPlayer();
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }
}
