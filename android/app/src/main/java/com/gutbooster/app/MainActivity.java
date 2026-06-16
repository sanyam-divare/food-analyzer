package com.gutbooster.app;

import android.content.res.Configuration;
import android.os.Bundle;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Force normal font scale before super.onCreate
        enforceFontScale();
        super.onCreate(savedInstanceState);

        WebView webView = getBridge().getWebView();
        WebSettings settings = webView.getSettings();

        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setTextZoom(100);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.grant(request.getResources());
            }
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
