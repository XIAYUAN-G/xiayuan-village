package cloud.xiayuanguide.app;

import android.content.res.AssetManager;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URL;
import java.net.URLDecoder;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 内置本地服务器：静态页面从内部存储的 web/ 目录读取（离线可用，首次启动由 MainActivity 解压），
 * /api/ 请求转发到 https://xiayuanguide.cloud（在线时登录/资料同步照常），离线返回 503。
 * 仅监听 127.0.0.1，外部设备无法访问。
 */
public class OfflineServer {

    public interface Logger {
        void log(String message);
    }

    private static final String HOST_KEY = "xiayuanguide.cloud";
    private static final String HOME_FILE = "厦园新手村·一站式导航.html";

    private final File webRoot;
    private final Logger logger;
    private final ServerSocket serverSocket;
    private final ExecutorService pool;
    private volatile boolean running = true;
    public final int port;

    public OfflineServer(AssetManager assets, Logger logger) throws IOException {
        this.assets = assets;
        this.logger = logger;
        this.serverSocket = new ServerSocket(0, 64, InetAddress.getByName("127.0.0.1"));
        this.port = serverSocket.getLocalPort();
        this.pool = Executors.newCachedThreadPool();
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                acceptLoop();
            }
        }, "offline-server");
        t.setDaemon(true);
        t.start();
    }

    private void acceptLoop() {
        while (running) {
            try {
                final Socket socket = serverSocket.accept();
                pool.execute(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            handle(socket);
                        } catch (Throwable ignored) {
                        } finally {
                            try { socket.close(); } catch (Exception ignored) {}
                        }
                    }
                });
            } catch (IOException e) {
                if (running && logger != null) logger.log("accept 失败: " + e);
                break;
            }
        }
    }

    public void stop() {
        running = false;
        try { serverSocket.close(); } catch (Exception ignored) {}
        pool.shutdownNow();
    }

    private void handle(Socket socket) {
        try {
            socket.setSoTimeout(15000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            String requestLine = readLine(in);
            if (requestLine == null || requestLine.length() == 0) return;
            String[] parts = requestLine.split(" ");
            if (parts.length < 2) return;
            String method = parts[0].toUpperCase(Locale.US);
            String rawPath = parts[1];

            Map<String, String> headers = new HashMap<String, String>();
            String line;
            while ((line = readLine(in)) != null && line.length() > 0) {
                int idx = line.indexOf(':');
                if (idx > 0) {
                    headers.put(line.substring(0, idx).trim().toLowerCase(Locale.US),
                            line.substring(idx + 1).trim());
                }
            }

            byte[] body = null;
            String cl = headers.get("content-length");
            if (cl != null) {
                try {
                    int n = Integer.parseInt(cl);
                    if (n > 0 && n < 32 * 1024 * 1024) {
                        body = readFully(in, n);
                    }
                } catch (NumberFormatException ignored) {}
            }

            if (rawPath.startsWith("/api/")) {
                proxy(method, rawPath, headers, body, out);
            } else {
                serveStatic(method, rawPath, out);
            }
        } catch (Throwable ignored) {
        }
    }

    /** /api/* → 转发云端；失败（离线）返回 503 */
    private void proxy(String method, String rawPath, Map<String, String> headers,
                       byte[] body, OutputStream out) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL("https://" + HOST_KEY + rawPath);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod(method);
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(15000);
            String[] keep = {"authorization", "content-type", "accept", "user-agent"};
            for (String k : keep) {
                String v = headers.get(k);
                if (v != null && !"user-agent".equals(k)) conn.setRequestProperty(k, v);
            }
            if (body != null && !"GET".equals(method) && !"HEAD".equals(method)) {
                conn.setDoOutput(true);
                OutputStream cos = conn.getOutputStream();
                cos.write(body);
                cos.flush();
                cos.close();
            }
            int status = conn.getResponseCode();
            String ctype = conn.getContentType();
            out.write(("HTTP/1.1 " + status + " OK\r\n").getBytes("UTF-8"));
            if (ctype != null) out.write(("Content-Type: " + ctype + "\r\n").getBytes("UTF-8"));
            InputStream ris = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            if (ris == null) ris = conn.getInputStream();
            byte[] resp = readFully(ris, Integer.MAX_VALUE);
            out.write(("Content-Length: " + resp.length + "\r\n").getBytes("UTF-8"));
            out.write("Connection: close\r\n\r\n".getBytes("UTF-8"));
            if (!"HEAD".equals(method)) out.write(resp);
            out.flush();
        } catch (Throwable e) {
            // 离线或云端不可达
            try {
                byte[] resp = "{\"error\":\"offline\",\"message\":\"当前离线，联网后可同步\"}".getBytes("UTF-8");
                out.write("HTTP/1.1 503 Service Unavailable\r\n".getBytes("UTF-8"));
                out.write("Content-Type: application/json; charset=utf-8\r\n".getBytes("UTF-8"));
                out.write("X-Offline: 1\r\n".getBytes("UTF-8"));
                out.write(("Content-Length: " + resp.length + "\r\n").getBytes("UTF-8"));
                out.write("Connection: close\r\n\r\n".getBytes("UTF-8"));
                if (!"HEAD".equals(method)) out.write(resp);
                out.flush();
            } catch (Throwable ignored) {}
            if (logger != null) logger.log("API 离线转发失败: " + rawPath);
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /** 静态资源 → APK assets/web/ */
    private void serveStatic(String method, String rawPath, OutputStream out) {
        try {
            String path = rawPath;
            int q = path.indexOf('?');
            if (q >= 0) path = path.substring(0, q);
            path = URLDecoder.decode(path, "UTF-8");
            while (path.startsWith("/")) path = path.substring(1);
            if (path.length() == 0) path = HOME_FILE;
            if (path.endsWith("/")) path = path + HOME_FILE;
            if (path.contains("..")) { sendError(out, 400, "bad request"); return; }

            byte[] data;
            try {
                InputStream is = assets.open("web/" + path);
                data = readFully(is, 64 * 1024 * 1024);
                is.close();
            } catch (IOException e) {
                sendError(out, 404, "not found: " + path);
                return;
            }

            out.write("HTTP/1.1 200 OK\r\n".getBytes("UTF-8"));
            out.write(("Content-Type: " + mime(path) + "\r\n").getBytes("UTF-8"));
            out.write(("Content-Length: " + data.length + "\r\n").getBytes("UTF-8"));
            out.write("Cache-Control: no-cache\r\n".getBytes("UTF-8"));
            out.write("Connection: close\r\n\r\n".getBytes("UTF-8"));
            if (!"HEAD".equals(method)) out.write(data);
            out.flush();
        } catch (Throwable e) {
            try { sendError(out, 500, "server error"); } catch (Throwable ignored) {}
        }
    }

    private void sendError(OutputStream out, int code, String msg) throws IOException {
        byte[] resp = msg.getBytes("UTF-8");
        out.write(("HTTP/1.1 " + code + " Error\r\n").getBytes("UTF-8"));
        out.write("Content-Type: text/plain; charset=utf-8\r\n".getBytes("UTF-8"));
        out.write(("Content-Length: " + resp.length + "\r\n").getBytes("UTF-8"));
        out.write("Connection: close\r\n\r\n".getBytes("UTF-8"));
        out.write(resp);
        out.flush();
    }

    private static String mime(String path) {
        String p = path.toLowerCase(Locale.US);
        if (p.endsWith(".html") || p.endsWith(".htm")) return "text/html; charset=utf-8";
        if (p.endsWith(".js")) return "application/javascript; charset=utf-8";
        if (p.endsWith(".css")) return "text/css; charset=utf-8";
        if (p.endsWith(".json")) return "application/json; charset=utf-8";
        if (p.endsWith(".webp")) return "image/webp";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
        if (p.endsWith(".gif")) return "image/gif";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".ico")) return "image/x-icon";
        if (p.endsWith(".pdf")) return "application/pdf";
        if (p.endsWith(".ttf")) return "font/ttf";
        if (p.endsWith(".woff")) return "font/woff";
        if (p.endsWith(".woff2")) return "font/woff2";
        if (p.endsWith(".txt")) return "text/plain; charset=utf-8";
        if (p.endsWith(".mp3")) return "audio/mpeg";
        if (p.endsWith(".mp4")) return "video/mp4";
        return "application/octet-stream";
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int prev = -1, c;
        while ((c = in.read()) != -1) {
            if (prev == '\r' && c == '\n') break;
            if (prev != -1) buf.write(prev);
            prev = c;
        }
        if (prev != -1 && (c == -1 || !(prev == '\r' && c == '\n'))) buf.write(prev);
        if (buf.size() == 0 && c == -1) return null;
        return buf.toString("UTF-8").trim();
    }

    private static byte[] readFully(InputStream in, int max) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[16 * 1024];
        int n, total = 0;
        while ((n = in.read(chunk)) != -1) {
            total += n;
            if (total > max) break;
            buf.write(chunk, 0, n);
        }
        return buf.toByteArray();
    }
}
