# openlife.beyondego.me（新生产）1Panel + nginx 配置指南

> **适用**：v1.5.1 → v1.6.0 生产迁移，新服务器建站（2026-08-21）
> **改写自**：`0705-nginx-prod.md`（xunlu 站），本文档所有路径/域名已替换为 openlife
> **配套**：`0821-迁移计划-v1.5.1-to-v1.6.0.md` Step 6 / Step 9 / Step 10

---

## 0. 总体结构（先看懂再动手）

```
用户 → https://openlife.beyondego.me
         ├── location ^~ /api/  → http://127.0.0.1:8000（FastAPI 后端，流式）
         └── location ^~ /      → http://127.0.0.1:3000（Next.js 前端）
```

- nginx 跑在 1Panel 的 **OpenResty docker 容器**里，容器名因 1Panel 安装而异（旧生产是 `1Panel-openresty-UpQ6`，**新服务器几乎必然不同，必须先查**）
- 维护模式靠 flag 文件切换，nginx 一次配好后不再动
- 旧域名（`xunlu.soulhappylab.com` / `xunlu.beyondego.me`）在**旧服务器**上改 301，见 §6

---

## 1. 前置确认（新服务器上执行，2 分钟）

```bash
# ① 查 OpenResty 容器名（记下来，后面要用）
docker ps --format '{{.Names}}' | grep -i openresty

# ② 查宿主机 www 挂载路径（1Panel 版本不同路径不同！）
docker inspect 【容器名】 | grep -B2 -A2 '"Destination": "/www"'
# 输出里的 Source 就是宿主机路径，可能是：
#   /opt/1panel/www                        （新版，无中间层）
#   /opt/1panel/apps/openresty/openresty/www （旧版，有中间层）
```

> 下文统一按 **无中间层 `/opt/1panel/www`** 写；如果你查出来有中间层，把所有 `/opt/1panel/www` 替换成实际路径。**容器视角一律是 `/www`**。

---

## 2. DNS 先行（域名控制台）

1. `openlife.beyondego.me` → A 记录 → **新服务器公网 IP**，TTL 先调 **300**（秒）
2. 等 1~2 分钟，本地 `ping openlife.beyondego.me` 确认解析到新 IP
3. ⚠️ 不先指过来，下一步 Let's Encrypt 证书签不出来

---

## 3. 1Panel 建站（网页操作）

1. **1Panel → 网站 → 新建网站**
   - 类型：**反向代理**
   - 主域名：`openlife.beyondego.me`
   - 代理地址先随便填 `http://127.0.0.1:3000`（后面再补第二条）
2. **申请 TLS 证书**：网站 → openlife → **证书** → Let's Encrypt → 申请（勾选自动续签）
3. **强制 HTTPS**：网站 → openlife → 配置里确认开启了 HTTP → HTTPS 跳转（下面文件 1 里已含）

建完后 1Panel 会自动生成站点目录 `/www/sites/openlife/`（容器视角）。

---

## 4. 反向代理：两条（网页操作 + 配置内容）

### 4.1 第一条 `/` → 前端（建站时已建，编辑它）

1Panel → 网站 → openlife → **反向代理** → 找到 `/` 那条 → 编辑 → 目标 `http://127.0.0.1:3000`，然后点「**编辑配置文件**」整段替换为：

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

### 4.2 第二条 `/api/` → 后端（新建）

1Panel → 网站 → openlife → **反向代理** → **新建**：
- 名称：`api`
- 匹配路径：`^~ /api/`
- 目标：`http://127.0.0.1:8000`

然后「**编辑配置文件**」整段替换为（流式必需，和 `deploy/nginx-api-stream.conf` 一致 + 维护拦截行）：

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
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Forwarded-Proto $scheme;

    # 流式接口（LLM SSE）必须关闭缓冲，否则 502 或卡住
    proxy_buffering off;
    proxy_cache off;
    proxy_request_buffering off;

    # LLM 流式生成较慢，超时 300s 以上
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;

    add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
}
```

⚠️ **关键坑**：这两条反代最终落在 `/www/sites/openlife/proxy/*.conf` 里被主配置 include——所以维护拦截的 `if` 行**必须加在这两个文件内部第一行**，加在主配置里没用。

---

## 5. 主配置：加维护模式检测块

1Panel → 网站 → openlife → **配置**（主 server 块），在 `error_log` 那行之后、其他 `location` 之前，插入这一段（其他内容一律不动）：

```nginx
    # ───── 维护模式检测（必须在 server 块内、location 之前）─────
    # 三段独立逻辑，千万别合并 if，nginx 的 if 是 evil
    set $maintenance_on 0;
    if (-f /www/sites/openlife/maintenance.flag) {
        set $maintenance_on 1;
    }
    if ($http_cookie ~* "bypass_maintenance=1") {
        set $maintenance_on 0;
    }
    error_page 503 @maintenance;
    location @maintenance {
        root /www/sites/openlife/maintenance;
        try_files /maintenance.html =503;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
    }
```

同时确认主配置里 `server_name` 只有新域名：

```nginx
server_name openlife.beyondego.me;
```

保存后创建维护页目录（**宿主机**执行）：

```bash
mkdir -p /opt/1panel/www/sites/openlife/maintenance   # 有中间层就换成实际路径
chmod 755 /opt/1panel/www/sites/openlife/maintenance
```

最后把维护变量填进 `.env.prod`（注意容器名换成 §1 查到的）：

```bash
MAINTENANCE_FLAG_PATH=/opt/1panel/www/sites/openlife/maintenance.flag
MAINTENANCE_PAGE_DIR=/opt/1panel/www/sites/openlife/maintenance
MAINTENANCE_TEMPLATE_PATH=/home/gitclone/BeingDoing/src/frontend/maintenance.html
NGINX_RELOAD_CMD="docker exec 【新容器名】 nginx -s reload"   # 留空则自动探测
BYPASS_COOKIE_NAME=bypass_maintenance
```

---

## 6. 旧站 301 跳转（旧服务器上操作，切流当天执行）

⚠️ 在**旧服务器**的 1Panel 上改 xunlu 站，不是新服务器。等**新站验收全部通过后再做**：

1Panel → 网站 → xunlu → 配置 → 主 server 块整段替换为：

```nginx
server {
    listen 80;
    listen 443 ssl;
    server_name xunlu.soulhappylab.com xunlu.beyondego.me;

    # SSL 证书配置保持原样（从旧配置里保留这两行和 ssl 相关行）
    ssl_certificate /www/sites/xunlu/ssl/fullchain.pem;
    ssl_certificate_key /www/sites/xunlu/ssl/privkey.pem;

    # 全站 301 到新域名（保留路径和查询参数，老链接/书签不丢）
    return 301 https://openlife.beyondego.me$request_uri;
}
```

---

## 7. 验证（全部用 curl，别信浏览器缓存）

```bash
# ① 站点通：预期 200
curl -sI https://openlife.beyondego.me | head -3

# ② 后端经反代通：预期 200（Swagger）
curl -sI https://openlife.beyondego.me/docs | head -3

# ③ 维护模式 on：预期 503
bash /home/gitclone/BeingDoing/scripts/maintenance.sh on \
  --end "2026-08-22 04:00" --reason "上线部署" --env prod
curl -sI https://openlife.beyondego.me | head -1          # HTTP/2 503
curl -sI https://openlife.beyondego.me/api/v1/xxx | head -1  # 也 503

# ④ 管理员绕过：带 cookie 预期 200
curl -sI -H "Cookie: bypass_maintenance=1" https://openlife.beyondego.me | head -1

# ⑤ 维护模式 off：预期恢复 200
bash /home/gitclone/BeingDoing/scripts/maintenance.sh off --env prod

# ⑥ 配置真的生效了（容器内核对，容器名换成实际值）
docker exec 【容器名】 grep -c "maintenance_on" /usr/local/openresty/nginx/conf/conf.d/openlife.conf   # 预期 ≥3
docker exec 【容器名】 grep -l "maintenance_on" /www/sites/openlife/proxy/*.conf                        # 预期列出 2 个文件

# ⑦ 旧域名 301（切流后）
curl -sI https://xunlu.soulhappylab.com | head -3   # 301 + Location: https://openlife.beyondego.me...
```

⚠️ **注意**：维护模式开启期间**支付宝回调也会被 503**（`/api/` 整段拦截）。支付宝会自动重试，但支付联调和切流期间不要开维护模式。

---

## 8. 常见问题

| 问题 | 排查 |
|------|------|
| 保存主配置报 `set directive is not allowed here` | `set $maintenance_on 0;` 必须写在 `server { }` 内部 |
| 反代改了不生效 | 改的是 `proxy/*.conf` 里的文件，不是主配置；`docker exec 【容器名】 ls /www/sites/openlife/proxy/` 确认 |
| 维护开了但没拦截 | `if` 行必须在 location 内部**第一行**（proxy_pass 之前） |
| 流式对话卡住/502 | 检查 `/api/` 反代是否有 `proxy_buffering off` + `proxy_read_timeout 300s` |
| 证书签不下来 | DNS A 记录还没生效 / 80 端口没放行；签好后记得开自动续签 |
| 浏览器看到旧页面 | 缓存问题，用无痕窗口 + F12 Disable cache，或直接 curl 验证 |
| 管理员被维护页拦了 | 浏览器 Console：`document.cookie='bypass_maintenance=1;path=/;max-age=86400;domain=.beyondego.me'` 后刷新 |
