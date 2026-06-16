package com.gutbooster.app;

import android.content.res.Configuration;
import android.os.Bundle;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.Bridge;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        enforceFontScale();
        super.onCreate(savedInstanceState);

        // Must be set AFTER super.onCreate
        Bridge bridge = getBridge();
        if (bridge == null) return;

        WebView webView = bridge.getWebView();
        if (webView == null) return;

        WebSettings settings = webView.getSettings();
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setTextZoom(100);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);

        // Override WebChromeClient AFTER Capacitor sets its own
        webView.post(() -> {
            webView.setWebChromeClient(new WebChromeClient() {
                @Override
                public void onPermissionRequest(PermissionRequest request) {
                    // Grant ALL permissions requested by web content
                    request.grant(request.getResources());
                }
            });
        });
    }

    private void enforceFontScale() {
        Configuration config = getResources().getConfiguration();
        config.fontScale = 1.0f;
        getResources().updateConfiguration(config,
            getResources().getDisplayMetrics());
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        newConfig.fontScale = 1.0f;
        getResources().updateConfiguration(newConfig,
            getResources().getDisplayMetrics());
        super.onConfigurationChanged(newConfig);
    }
}
