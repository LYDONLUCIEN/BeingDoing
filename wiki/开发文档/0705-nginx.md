# career.soulhappylab.com nginx 配置（含维护模式拦截）

**用途**：1Panel → 网站 → zhiyinapp → 配置 → 粘贴整段替换。
**对应仓库**：`/home/gitclone/BeingDoing`
**维护机制**：脚本只切 `/www/sites/zhiyinapp/maintenance.flag` 文件存在与否，nginx 配置一次性加好后不再动。

> **⚠️ dev/prod 不要混用配置**：这是 **dev 机**（career / zhiyinapp）的配置。
> - dev 容器名：`1Panel-openresty-hjWm`，宿主机 www 路径：`/opt/1panel/apps/openresty/openresty/www`
> - prod 容器名：`1Panel-openresty-UpQ6`，宿主机 www 路径：`/opt/1panel/www`（**无中间层**，1Panel 版本不同）
> - prod（xunlu）配置见 [`0705-nginx-prod.md`](./0705-nginx-prod.md)，**不要把本文档的路径模板直接搬到 prod**。

---

## 完整配置（直接复制粘贴到 1Panel）

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    # 双域名并存：soulhappylab.com 与 beyondego.me 同时可用
    # 注意：SSL 证书需同时覆盖两个域名（可申请多域名 SAN 证书，或两张证书选其一指向）
    server_name soulhappylab.com www.soulhappylab.com career.soulhappylab.com career.beyondego.me;

    index index.php index.html index.htm default.php default.htm default.html;

    access_log /www/sites/zhiyinapp/log/access.log main;
    error_log /www/sites/zhiyinapp/log/error.log;

    # ─────────────────────────────────────────────────────
    # 维护模式检测（必须在 server 块内、location 之前）
    # 三段独立逻辑，千万别合并 if，nginx 的 if 是 evil
    # ─────────────────────────────────────────────────────
    set $maintenance_on 0;
    if (-f /www/sites/zhiyinapp/maintenance.flag) {
        set $maintenance_on 1;
    }
    if ($http_cookie ~* "bypass_maintenance=1") {
        set $maintenance_on 0;
    }
    error_page 503 @maintenance;
    location @maintenance {
        root /www/sites/zhiyinapp/maintenance;
        try_files /maintenance.html =503;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
    }

    location ^~ /.well-known/acme-challenge {
        allow all;
        root /usr/share/nginx/html;
    }

    # 1) Next hashed 静态资源：长缓存（不拦截，维护页是纯静态 HTML 用不到）
    location ^~ /_next/static/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;

        expires 365d;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
    }

    # 2) API 直接走后端（关键，避免 /api 在 Next 链路里绕）
    location ^~ /api/ {
        if ($maintenance_on = 1) { return 503; }
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_connect_timeout 60s;

        add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
    }

    # 3) 页面请求走 Next，HTML 不缓存
    location / {
        if ($maintenance_on = 1) { return 503; }
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
    }

    # 4) 限流先放宽（关键）
    limit_conn perserver 300;
    limit_conn perip 100;
    # limit_rate 512k;  # 先注释，稳定后再开

    if ($scheme = http) {
        return 301 https://$host$request_uri;
    }

    ssl_certificate /www/sites/zhiyinapp/ssl/fullchain.pem;
    ssl_certificate_key /www/sites/zhiyinapp/ssl/privkey.pem;
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:!aNULL:!eNULL:!EXPORT:!DSS:!DES:!RC4:!3DES:!MD5:!PSK:!KRB5:!SRP:!CAMELLIA:!SEED;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    error_page 497 https://$host$request_uri;
    add_header Strict-Transport-Security "max-age=31536000" always;

    include /www/sites/zhiyinapp/redirect/*.conf;
}
```

---

## 关键改动总结（与原版差异）

### 新增 1：维护模式检测块（在 `error_log` 之后、`location ^~ /.well-known` 之前）

```nginx
set $maintenance_on 0;
if (-f /www/sites/zhiyinapp/maintenance.flag) {
    set $maintenance_on 1;
}
if ($http_cookie ~* "bypass_maintenance=1") {
    set $maintenance_on 0;
}
error_page 503 @maintenance;
location @maintenance {
    root /www/sites/zhiyinapp/maintenance;
    try_files /maintenance.html =503;
    add_header Cache-Control "no-store, no-cache, must-revalidate" always;
}
```

### 新增 2：`location ^~ /api/` 内部第一行

```nginx
if ($maintenance_on = 1) { return 503; }
```

### 新增 3：`location /` 内部第一行

```nginx
if ($maintenance_on = 1) { return 503; }
```

### 不动：`location ^~ /_next/static/`

维护页是纯静态 HTML，不依赖 Next 资源，无需拦截。

---

## nginx if 的 3 个坑（踩过的总结）

1. **不能嵌套**：`if` 里不能放 `if`
2. **不能合并**：多个条件要写多个 `if`，不要试图用一个 `if` 处理两件事
3. **`set` 在 `if` 块内会污染外层变量**：所以 `set $maintenance_on 1` 在 if 里写，外层读得到（这是预期行为，但也是 nginx if 容易出错的原因）

---

## 验证步骤

### 1. 1Panel 保存配置（自动 reload nginx）

无报错 = 配置语法正确。

### 2. CLI 进入维护

```bash
bash /home/gitclone/BeingDoing/scripts/maintenance.sh on \
  --end "2026-07-05 04:00" \
  --reason "数据库升级" \
  --env dev
```

### 3. 验证用户视角（无痕窗口）

开无痕窗口访问 `https://career.soulhappylab.com` → **应看到维护页**。

### 4. 验证管理员绕过

普通浏览器 Console：
```javascript
// 按你当前访问的域名选一条
document.cookie='bypass_maintenance=1;path=/;max-age=86400;domain=.soulhappylab.com'
document.cookie='bypass_maintenance=1;path=/;max-age=86400;domain=.beyondego.me'
```
刷新 → **应看到真实站点**。

### 5. 退出维护

```bash
bash /home/gitclone/BeingDoing/scripts/maintenance.sh off --env dev
```

无痕窗口再访问 → **应看到真实站点**。

---

## 常见问题

### Q: 1Panel 报「invalid number of arguments in ssl_ciphers」
A: 复制粘贴时 `ssl_ciphers` 那行被换行符截断了。**整段配置一次性粘贴**，不要分行复制。

### Q: 报「set directive is not allowed here」
A: `set $maintenance_on 0;` 必须在 `server { }` 内部。检查是否被误放到了 server 块外（文件开头）。

### Q: 配置保存成功，但维护模式不拦截
A: 检查 `if ($maintenance_on = 1) { return 503; }` 是否在 `location` 内部第一行（proxy_pass 之前）。

### Q: 配置里 `set $maintenance_on 1; set $maintenance_on 0;` 同时存在
A: 这是合并 if 的 bug，参考上文「nginx if 的 3 个坑」。

---

## 仓库内相关文件

| 文件 | 作用 |
|------|------|
| `src/frontend/maintenance.html` | 维护页模板（含占位符 `data-slot="reason"` / `data-slot="end_at"`） |
| `scripts/maintenance.sh` | 维护模式切换脚本（on / off / status） |
| `start.sh` | 加了 `maintenance` 子命令 + `--maintenance` flag |
| `.env.dev` | 维护相关路径变量（宿主机视角） |
| `src/backend/app/api/v1/admin_maintenance.py` | admin 后台调脚本的 API |
| `src/frontend/app/(main)/admin/site-notices/page.tsx` | admin UI 维护模式卡片 |
