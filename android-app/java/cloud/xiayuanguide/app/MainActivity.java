package cloud.xiayuanguide.app;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.view.KeyEvent;
import android.view.View;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {

    /** 云端主机：站外链接跳系统浏览器 / 深链接路径映射到本地 */
    private static final String HOST = "xiayuanguide.cloud";

    private OfflineServer server;
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (Build.VERSION.SDK_INT >= 21) {
            Window w = getWindow();
            w.setStatusBarColor(Color.parseColor("#505653"));
            w.setNavigationBarColor(Color.parseColor("#505653"));
        }

        try {
            server = new OfflineServer(getAssets(), new OfflineServer.Logger() {
                @Override
                public void log(String message) {
                    // 预留：可接 LogCat 调试
                }
            });
        } catch (Exception e) {
            server = null;
        }

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setSupportZoom(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        if (Build.VERSION.SDK_INT >= 21) {
            CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);
        }

        web.setBackgroundColor(Color.parseColor("#FAF6EC"));
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String host = uri.getHost() == null ? "" : uri.getHost();
                if ("127.0.0.1".equals(host) || "localhost".equals(host)) return false;
                openExternal(uri);
                return true;
            }
        });

        web.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String disposition, String mime, long size) {
                downloadOrOpen(Uri.parse(url), mime);
            }
        });

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(startUrl(getIntent()));
        }
    }

    /** 启动地址：深链接 https://xiayuanguide.cloud/xxx → 本地 /xxx；默认首页 */
    private String startUrl(Intent intent) {
        String base = "http://127.0.0.1:" + (server != null ? server.port : 8099) + "/";
        Uri data = intent != null ? intent.getData() : null;
        if (data != null && "https".equals(data.getScheme()) && HOST.equals(data.getHost())) {
            String path = data.getPath() == null ? "" : data.getPath();
            return base + path.substring(path.startsWith("/") ? 1 : 0)
                    + (data.getQuery() != null ? "?" + data.getQuery() : "");
        }
        return base;
    }

    private void downloadOrOpen(Uri uri, String mime) {
        try {
            DownloadManager.Request req = new DownloadManager.Request(uri);
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            String name = URLUtil.guessFileName(uri.toString(), null, mime);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            if (mime != null && mime.length() > 0) req.setMimeType(mime);
            String cookie = CookieManager.getInstance().getCookie(uri.toString());
            if (cookie != null) req.addRequestHeader("Cookie", cookie);
            DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            dm.enqueue(req);
        } catch (Exception e) {
            openExternal(uri);
        }
    }

    private void openExternal(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception ignored) {
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.loadUrl("about:blank");
            web.destroy();
            web = null;
        }
        if (server != null) {
            server.stop();
            server = null;
        }
        super.onDestroy();
    }
}
