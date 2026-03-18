# Admin 子域（方案 B）逐步执行手册

> 目标：把 `admin.soulhappylab.com` 安全接入到现有 BeingDoing 服务。  
> 适用阶段：M1（安全底座与访问入口）。  
> 使用方式：按顺序做，做完就打勾。不要跳步。

---

## 0. 执行前安全准备（先做）

- [ ] **确认当前业务可用**：`career.soulhappylab.com` 当前访问正常
- [ ] **截图备份 1Panel 现有站点配置**（整页截图）
- [ ] **导出当前 Nginx 配置副本**（1Panel 里复制保存到本地）
- [ ] **备份项目关键文件**
  - [ ] `/home/gitclone/BeingDoing/.env`
  - [ ] `/home/gitclone/BeingDoing/start.sh`
  - [ ] `/home/gitclone/BeingDoing/deploy/systemd/*`
- [ ] **记录当前可用回滚点**（例如：Git commit id / 时间点）

---

## 1. DNS 配置（域名解析）

### 你要做的操作

- [x] 登录你的 DNS 服务商控制台（阿里云/腾讯云/Cloudflare 等）
- [x] 新增一条 `A` 记录：
  - 主机记录：`admin`
  - 记录值：你的服务器公网 IP
  - TTL：默认即可（推荐 600s）
- [x] 保存后等待生效（通常 1-10 分钟，最慢可到 30 分钟）

### 验证标准

- [x] `admin.soulhappylab.com` 已能解析到你的服务器 IP

---

## 2. 1Panel 新建 admin 站点（不要改旧站点）

### 你要做的操作

- [x] 在 1Panel 新建一个站点（推荐单独站点，不要覆盖现有 `career`）
- [x] 绑定域名：`admin.soulhappylab.com`
- [x] 开启 HTTPS（先申请证书后再强制跳转）

### 验证标准

- [x] 站点已创建且无语法报错
- [x] 访问 `https://admin.soulhappylab.com` 能返回页面（哪怕是默认页也可以）

---

## 3. SSL 证书

### 你要做的操作

- [x] 在 1Panel 为 `admin.soulhappylab.com` 申请 Let’s Encrypt 证书
- [x] 启用证书到 admin 站点
- [x] 开启 HTTP -> HTTPS 跳转

### 验证标准

- [x] 浏览器访问 admin 子域证书正常（无不安全提示）
- [x] `http://admin.soulhappylab.com` 会自动跳到 `https://`

---

## 4. 反向代理路由（核心）

> 目标：同一子域下，页面走前端，API 走后端。

### 你要做的操作

- [ ] 在 admin 站点反代规则中配置：
  - [ ] 路径 `/` -> `http://127.0.0.1:3000`（Next 前端）
  - [ ] 路径 `/api` -> `http://127.0.0.1:8000`（FastAPI 后端）
- [ ] 确认转发头保留：
  - [ ] `Host`
  - [ ] `X-Forwarded-For`
  - [ ] `X-Real-IP`
  - [ ] `X-Forwarded-Proto`

### 验证标准

- [ ] `https://admin.soulhappylab.com/` 能打开前端页面
- [ ] `https://admin.soulhappylab.com/api/v1/health`（或任意可访问接口）有后端响应

---

## 5. 安全增强（M1 最小必做）

### 你要做的操作

- [ ] 对 `/admin` 和 `/api/v1/admin` 增加更严格限流
- [ ] （推荐）加 `IP 白名单`：
  - 仅允许你的固定 IP 访问 admin 子域
  - 若你的 IP 不固定，可先不做

### 验证标准

- [ ] 正常访问不受影响
- [ ] 异常高频请求被限制

---

## 6. 应用配置调整（你做配置，我来改代码）

### 你要做的操作

- [ ] 在 `.env` 保持或确认：
  - [x] `NEXT_PUBLIC_API_URL=`（建议留空，走同域 `/api`）
  - [x] `SUPER_ADMIN_EMAILS=...` 包含你的管理员邮箱
- [ ] 重启服务（使用你现在的标准流程）：
  - [ ] `./start.sh restart backend`
  - [ ] `./start.sh restart frontend`

### 需要我做的代码项（由我执行）

- [x] 后端 CORS 加入：`https://admin.soulhappylab.com`
- [x] 全部 `/api/v1/admin/*` 路由统一强制 `super_admin` 校验
- [ ] （下一阶段 M2）加 step-up 二次验证

---

## 7. 联调检查（上线前）

### 你要做的操作

- [ ] 使用普通账号访问 `/admin`，应提示无权限/403
- [ ] 使用 super_admin 账号访问 `/admin`，应允许进入
- [ ] 检查 `/admin/activations` 数据可读
- [ ] 检查浏览器 Console 无明显 CORS 报错

---

## 8. 回滚步骤（出问题时按顺序）

### 快速回滚（1Panel）

- [ ] 回滚 admin 子域站点反代配置到上一个版本
- [ ] 若问题仍在，临时下线 admin 子域（不影响 `career` 主站）

### 代码回滚（仅必要时）

- [ ] 回滚最近一次 admin 相关代码提交
- [ ] 重启前后端服务
- [ ] 做最小验证：主站访问、登录、核心 API

---

## 9. 完成定义（M1 Done）

- [ ] `admin.soulhappylab.com` 可稳定访问
- [ ] API 在 admin 子域下可用
- [ ] 非 super_admin 无法访问 admin 接口
- [ ] 主站 `career.soulhappylab.com` 功能不受影响
- [ ] 已记录回滚点与配置截图

---

## 10. 执行记录（每次操作后填写）

```md
### [YYYY-MM-DD HH:mm] 执行记录
- 本次操作：
- 结果：
- 是否影响主站：
- 遇到问题：
- 下一步：
```

### [2026-03-18 15:45] 执行记录
- 本次操作：确认并完成 DNS、建站、SSL（步骤 1-3）；完成后端 CORS 与 admin 权限校验。
- 结果：admin 子域基础通路已具备，进入联调阶段（步骤 7-9）。
- 是否影响主站：无已知影响。
- 遇到问题：证书路径误写导致 Nginx 失败，已切回 `admin.soulhappylab.com` 正确路径。
- 下一步：完成步骤 5（限流/白名单）并执行步骤 7 联调。

