# admin.soulhappylab.com 403 排查

## 常见原因

### 1. 反向代理未配置

若 1Panel 中 admin 站点只绑定了域名、未配置反代，Nginx 会使用默认 root，目录为空时返回 **403 Forbidden**。

**解决**：在 1Panel → 站点 → admin.soulhappylab.com → 反向代理 中配置：

- 路径 `/` → `http://127.0.0.1:3000`（Next 前端）
- 路径 `/api` → `http://127.0.0.1:8000`（FastAPI 后端）

保留转发头：`Host`、`X-Forwarded-For`、`X-Real-IP`、`X-Forwarded-Proto`。

### 2. 根目录为空

若站点 root 指向空目录，Nginx 会返回 403。应使用反向代理，不要直接指向静态目录。

### 3. 后端 API 403

若页面能打开、但请求 `/api/v1/admin/*` 返回 403，则为权限问题：当前用户非超级管理员。检查 `.env` 中 `SUPER_ADMIN_EMAILS` 或 `SUPER_ADMIN_USER_IDS` 是否包含你的账号。

## 快速验证

```bash
# 主站是否正常
curl -I https://career.soulhappylab.com

# admin 子域（若反代未配，会 403）
curl -I https://admin.soulhappylab.com

# 直接测后端（需替换为实际后端地址）
curl -I http://127.0.0.1:8000/api/v1/health
```
