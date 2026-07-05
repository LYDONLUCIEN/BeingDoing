# xunlu.soulhappylab.com (生产) nginx 配置（含维护模式拦截）

**用途**：1Panel → 网站 → xunlu → 配置。
**对应仓库**：`/home/gitclone/BeingDoing`
**维护机制**：脚本切 `/www/sites/xunlu/maintenance.flag` 文件，nginx 一次性配好后不再动。

---

## ⚠ prod 配置的特殊性

xunlu 这个站点的反代 location(`location /` 和 `location ^~ /api/`)**不在主配置里**，而是通过：

```nginx
include /www/sites/xunlu/proxy/*.conf;
```

外部 include 进来的。所以维护拦截代码需要改 **3 个文件**：

| 文件 | 1Panel 路径 | 改动 |
|------|------------|------|
| **主配置** | 网站 → xunlu → 配置（主 server 块） | 加维护检测块（set/if/error_page/@maintenance） |
| **`/` 反代** | 网站 → xunlu → 反向代理 → `default.conf`(或 `/` 对应文件) | 在 `location ^~ /` 内部第一行加 if |
| **`/api/` 反代** | 网站 → xunlu → 反向代理 → `api.conf`(或 `/api/` 对应文件) | 在 `location ^~ /api/` 内部第一行加 if |

---

## 容器内实际路径（用于脚本/诊断）

**⚠️ prod 机 1Panel 版本与 dev 不同，容器挂载是 `/opt/1panel/www → /www`（无 `apps/openresty/openresty` 中间层）。容器名 `1Panel-openresty-UpQ6`（不是 dev 机的 `hjWm`）。**

| 用途 | 路径 |
|------|------|
| 主配置 | `/usr/local/openresty/nginx/conf/conf.d/xunlu.conf` |
| 反代 include 目录 | `/www/sites/xunlu/proxy/` |
| 维护 flag（容器内） | `/www/sites/xunlu/maintenance.flag` |
| 维护页目录（容器内） | `/www/sites/xunlu/maintenance/` |
| 维护 flag（宿主机） | `/opt/1panel/www/sites/xunlu/maintenance.flag` |
| 维护页目录（宿主机） | `/opt/1panel/www/sites/xunlu/maintenance/` |
| 容器名 | `1Panel-openresty-UpQ6`（prod），自动探测兜底见 `maintenance.sh` |

---

## 文件 1：主配置（直接整段替换 1Panel 主配置）

```nginx
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name xunlu.soulhappylab.com;

    index index.php index.html index.htm default.php default.htm default.html;

    access_log /www/sites/xunlu/log/access.log main;
    error_log /www/sites/xunlu/log/error.log;

    # ─────────────────────────────────────────────────────
    # 维护模式检测（必须在 server 块内、location 之前）
    # 三段独立逻辑，千万别合并 if，nginx 的 if 是 evil
    # ─────────────────────────────────────────────────────
    set $maintenance_on 0;
    if (-f /www/sites/xunlu/maintenance.flag) {
        set $maintenance_on 1;
    }
    if ($http_cookie ~* "bypass_maintenance=1") {
        set $maintenance_on 0;
    }
    error_page 503 @maintenance;
    location @maintenance {
        root /www/sites/xunlu/maintenance;
        try_files /maintenance.html =503;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
    }

    location ~ ^/(\.user\.ini|\.htaccess|\.git|\.env|\.svn|\.project|LICENSE|README\.md) {
        return 404;
    }
    location ^~ /.well-known/acme-challenge {
        allow all;
        root /usr/share/nginx/html;
    }
    if ( $uri ~ "^/\.well-known/.*\.(php|jsp|py|js|css|lua|ts|go|zip|tar\.gz|rar|7z|sql|bak)$" ) {
        return 403;
    }
    http2 on;
    if ($scheme = http) {
        return 301 https://$host$request_uri;
    }

    ssl_certificate /www/sites/xunlu/ssl/fullchain.pem;
    ssl_certificate_key /www/sites/xunlu/ssl/privkey.pem;
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA256:!aNULL:!eNULL:!EXPORT:!DSS:!DES:!RC4:!3DES:!MD5:!PSK:!KRB5:!SRP:!CAMELLIA:!SEED;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    error_page 497 https://$host$request_uri;
    proxy_set_header X-Forwarded-Proto https;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";

    #include /www/sites/xunlu/redirect/*.conf;
    include /www/sites/xunlu/proxy/*.conf;
}
```

### 与原版差异（只加了 1 段）

在 `error_log` 之后、`location ~ ^/(\.user\.ini...)` 之前，加了维护检测块：

```nginx
set $maintenance_on 0;
if (-f /www/sites/xunlu/maintenance.flag) {
    set $maintenance_on 1;
}
if ($http_cookie ~* "bypass_maintenance=1") {
    set $maintenance_on 0;
}
error_page 503 @maintenance;
location @maintenance {
    root /www/sites/xunlu/maintenance;
    try_files /maintenance.html =503;
    add_header Cache-Control "no-store, no-cache, must-revalidate" always;
}
```

**其他全部保持原样**（ssl_ciphers、http2、limit、HSTS 等都不要动）。

---

## 文件 2：`/` 反代配置（1Panel → 反向代理 → `/` 对应的 conf 文件）

**原始内容：**

```nginx
location ^~ / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header REMOTE-HOST $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_http_version 1.1;
    add_header X-Cache $upstream_cache_status;
    proxy_ssl_server_name off;
    proxy_ssl_name $proxy_host;
}
```

**改成（只在第一行加 `if ($maintenance_on = 1) { return 503; }`）：**

```nginx
location ^~ / {
    if ($maintenance_on = 1) { return 503; }
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header REMOTE-HOST $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_http_version 1.1;
    add_header X-Cache $upstream_cache_status;
    proxy_ssl_server_name off;
    proxy_ssl_name $proxy_host;
}
```

---

## 文件 3：`/api/` 反代配置（1Panel → 反向代理 → `/api/` 对应的 conf 文件）

**原始内容：**

```nginx
location ^~ /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Host $server_name;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;

    proxy_buffering off;
    proxy_cache off;
    proxy_request_buffering off;

    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;

    add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
}
```

**改成（只在第一行加 `if ($maintenance_on = 1) { return 503; }`）：**

```nginx
location ^~ /api/ {
    if ($maintenance_on = 1) { return 503; }
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Host $server_name;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;

    proxy_buffering off;
    proxy_cache off;
    proxy_request_buffering off;

    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;

    add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
}
```

---

## 1Panel 操作步骤

### 步骤 1：改主配置
1Panel → 网站 → `xunlu` → 配置 → **整段替换为「文件 1」** → 保存。

### 步骤 2：改 `/` 反代
1Panel → 网站 → `xunlu` → **反向代理** → 找到 `/` 那条 → 编辑配置 → **整段替换为「文件 2」** → 保存。

### 步骤 3：改 `/api/` 反代
1Panel → 网站 → `xunlu` → **反向代理** → 找到 `/api/` 那条 → 编辑配置 → **整段替换为「文件 3」** → 保存。

### 步骤 4：创建维护页目录（宿主机执行）

```bash
# ⚠️ prod 机容器挂载是 /opt/1panel/www → /www（无中间层）
mkdir -p /opt/1panel/www/sites/xunlu/maintenance
# 设置让后端进程能写入（脚本会用 sudo 或 root 身份写）
chmod 755 /opt/1panel/www/sites/xunlu/maintenance
```

### 步骤 5：填 `.env.prod` 维护相关变量

仓库根 `.env.prod` 加（如果还没有）：

```bash
# 维护模式（xunlu 生产环境）
# ⚠️ prod 机容器挂载是 /opt/1panel/www → /www（无 apps/openresty/openresty 中间层）
# 容器名：1Panel-openresty-UpQ6（prod），留空则 maintenance.sh 自动探测
MAINTENANCE_FLAG_PATH=/opt/1panel/www/sites/xunlu/maintenance.flag
MAINTENANCE_PAGE_DIR=/opt/1panel/www/sites/xunlu/maintenance
MAINTENANCE_TEMPLATE_PATH=/home/gitclone/BeingDoing/src/frontend/maintenance.html
NGINX_RELOAD_CMD="docker exec 1Panel-openresty-UpQ6 nginx -s reload"
BYPASS_COOKIE_NAME=bypass_maintenance
```

---

## 验证步骤（避免缓存欺骗）

### 1. CLI 进入维护

```bash
bash /home/gitclone/BeingDoing/scripts/maintenance.sh on \
  --end "2026-07-05 04:00" \
  --reason "数据库升级" \
  --env prod
```

### 2. 用 curl 验证（最可靠，无缓存）

```bash
# 用户视角：应返回 503 + 维护页 HTML
curl -sI https://xunlu.soulhappylab.com | head -5

# 管理员视角：带 bypass cookie，应返回 200
curl -sI -H "Cookie: bypass_maintenance=1" https://xunlu.soulhappylab.com | head -5
```

预期：
- 无 cookie → `HTTP/2 503` + `content-length: 3507`（维护页 HTML）
- 带 cookie → `HTTP/2 200`（真实站点）

### 3. 浏览器无痕窗口验证（需 Disable cache）

1. 开无痕窗口
2. **F12 → Network → 勾选 Disable cache**
3. 访问 `https://xunlu.soulhappylab.com`
4. 应看到维护页

### 4. 管理员绕过（Console 执行）

```javascript
document.cookie='bypass_maintenance=1;path=/;max-age=86400;domain=.soulhappylab.com'
```

刷新 → 应看到真实站点。

### 5. 退出维护

```bash
bash /home/gitclone/BeingDoing/scripts/maintenance.sh off --env prod
```

curl 再验证 → `HTTP/2 200`（所有人都能访问）。

---

## 容器内验证 nginx 配置真的改了

```bash
# 主配置应有 5 处 maintenance 相关
docker exec 1Panel-openresty-UpQ6 grep -c "maintenance_on\|maintenance.flag\|@maintenance" /usr/local/openresty/nginx/conf/conf.d/xunlu.conf

# / 反代文件应有 if 拦截
docker exec 1Panel-openresty-UpQ6 grep -l "maintenance_on" /www/sites/xunlu/proxy/*.conf
```

---

## 常见问题

### Q: 主配置保存时报「set directive is not allowed here」
A: `set $maintenance_on 0;` 必须在 `server { }` 内部。检查是否被误放到了 server 块外（文件开头）。

### Q: 反代 location 改了但没生效
A: 1Panel 的反代配置在 `proxy/*.conf` 里，必须改那里的文件，不是主配置。验证：
```bash
docker exec 1Panel-openresty-UpQ6 ls /www/sites/xunlu/proxy/
```

### Q: 维护模式开启但拦截不生效
A: 检查 `if ($maintenance_on = 1) { return 503; }` 是否在 location 内部第一行（proxy_pass 之前）。

### Q: 浏览器测试看到旧页面
A: 浏览器缓存。开无痕 + F12 → Network → Disable cache，或者直接用 curl 验证（curl 不缓存）。

### Q: 进入维护后我（管理员）也被拦截
A: 浏览器 Console 执行 `document.cookie='bypass_maintenance=1;path=/;max-age=86400;domain=.soulhappylab.com'`，刷新即可。

---

## 与 career 配置的差异

| 维度 | career (dev) | xunlu (prod) |
|------|--------------|--------------|
| server_name | soulhappylab.com / www / career | xunlu.soulhappylab.com |
| 站点目录 | `/www/sites/zhiyinapp/` | `/www/sites/xunlu/` |
| 维护 flag | `/www/sites/zhiyinapp/maintenance.flag` | `/www/sites/xunlu/maintenance.flag` |
| 反代 location | 在主配置里 | **在 `proxy/*.conf` include 里** |
| 限流 | `limit_conn perserver 300` | 无（看你原版没有） |
| HSTS | `max-age=31536000` | `max-age=31536000; includeSubDomains` |
| **容器名** | `1Panel-openresty-hjWm` | `1Panel-openresty-UpQ6` |
| **宿主机 www 路径** | `/opt/1panel/apps/openresty/openresty/www`（含中间层） | `/opt/1panel/www`（**无中间层**，1Panel 版本不同） |
| **MAINTENANCE_FLAG_PATH** | `/opt/1panel/apps/openresty/openresty/www/sites/zhiyinapp/maintenance.flag` | `/opt/1panel/www/sites/xunlu/maintenance.flag` |

**关键差异**:
1. xunlu 的反代 location 走 include，所以拦截 if 要加在 include 文件里，不是主配置。这是 prod 配置最容易踩坑的地方。
2. **dev/prod 容器挂载路径不一样**（1Panel 版本不同），不要把 dev 的 `.env` 路径模板硬搬到 prod。
3. **容器名不一样**（`hjWm` vs `UpQ6`），如不显式设 `NGINX_RELOAD_CMD`，`maintenance.sh` 会自动探测 `docker ps` 里的 `1Panel-openresty-*`。
