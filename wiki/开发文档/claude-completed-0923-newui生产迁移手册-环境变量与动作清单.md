# newui 生产迁移手册（环境变量与动作清单）

> 生成日期：2026-09-23
> 迁移范围：`origin/main (b9bfd4f 密码修改)` → `newui (5b3b09a 修复三处回归)`，共 14 个提交、190+ 文件
> 核心变化：全新 UI、报告渲染器唯一化为 xunlu（ADR-0021）、LLM 轮次诊断日志、admin 外观/模型分流配置页、静态资源长缓存

---

## 一、环境变量调整总表（重点）

### 1.1 需要删除的变量

| 变量 | 说明 |
|---|---|
| `RENDER_ENGINE` | **已从 settings.py 移除**（ADR-0021 删 weasyprint 简洁版开关）。三份 env 文件（.env / .env.dev / .env.prod）均未配置过，理论上无需动作；若生产机 shell profile 或部署脚本里有手动 export，请顺手清掉（残留无害，pydantic 忽略未知变量，但会误导排查） |

**结论：生产 env 文件不需要删任何行。**

### 1.2 需要新增的变量

| 变量 | 默认值 | 建议 | 说明 |
|---|---|---|---|
| `LLM_TURN_LOG_RETENTION_DAYS` | `30` | **可不配** | LLM 轮次诊断日志保留天数（`data/logs/llm_turns/*.jsonl`，**含 CoT 全文属敏感数据**）。每日 cron job 自动清理，main.py 的 APScheduler 随服务启动注册。`.env` L243 已有 `30`，与默认一致 |
| `LLM_TURN_LOG_CLEANUP_CRON` | `"0 5 * * *"` | **可不配** | 清理 job 的 cron。`.env` L244 已配，与默认一致 |
| `CHROME_PATH` | `None`（自动探测） | **按需** | xunlu 渲染器需要 Chrome/Chromium，自动探测 `/usr/bin/google-chrome` 等标准路径；仅当 Chrome 装在非标准路径时配置 |
| `MODEL_CONFIG_ENC_KEY` | `None`（回退 SECRET_KEY） | 可不动 | 模型配置 api_key 加密密钥。轮换会让历史密文不可解密，保持现状最稳 |

**结论：若 `.env` 与生产机同步（推荐先 `git pull` 再比对），新变量零配置即可生效。**

### 1.3 需要核对的变量

| 变量 | 现值（.env 基线） | 生产动作 |
|---|---|---|
| `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` | `.env:201` 已配 base64 值 | ✅ 确认存在即可。**必须是 `openssl rand -base64 32` 的输出值，不是命令文本**。start-run 清 `.next` 重建后，旧浏览器标签会报 Server Action 错误（硬刷新解决，属正常现象） |
| `SUPER_ADMIN_EMAILS` | `q510971228@gmail.com,q510971228@163.com` | ✅ 已是真实管理员邮箱。admin「轮次诊断」（新功能，查 CoT 全文）与 DEBUG_MODE 都依赖它。`.env.dev` 里多出的 `ui_preview_shot@test.com` 是 dev 截图专用，不进生产 |
| `SUPER_ADMIN_USER_IDS` | 空（用邮箱即可） | 无需动作 |
| `REPORT_RENDERER_DIR` / `REPORT_RENDERER_NODE` | 默认 `<repo>/src/report-renderer` / `node` | ✅ 默认即可，`dist/` 已 git tracked，`git pull` 即得，**生产不需要 npm install / build**（dist 是 esbuild bundle 产物，react 已打包在内） |

### 1.4 本次不涉及的部分（明确说明）

- **数据库**：无新增迁移。alembic 最新版本两边一致（`021_user_avatar`），models 无变化。跑 `alembic upgrade head` 幂等无害，可跑可不跑
- **Python 依赖**：requirements / pyproject 零变化，**不要卸载 weasyprint**（`export_service.py` 仍在用）
- **前端依赖**：package.json 零变化，无需 `npm install`
- 用户新开发中的「AI 模型分流」（llm_scene，工作区未提交）**不在本次迁移范围**，其变量要求见该功能自己的文档

---

## 二、系统运行时要求（本次最大风险点）

⚠️ **生产 PDF 引擎首次从 weasyprint 切换到 xunlu**：生产从未配置过 `RENDER_ENGINE`（一直默认 weasyprint），ADR-0021 删除开关后**强制全走 xunlu**（Node 子进程 + Chrome headless）。

上线前在生产机执行：

```bash
node --version          # 必须 ≥ 20（本 dev 机为 v20.20.2）
ls /usr/bin/google-chrome /usr/bin/chromium* 2>/dev/null   # 至少存在一个
```

任一不满足时的补救：
- 无 node / 版本过低：安装 Node 20，或在 `.env.prod` 配 `REPORT_RENDERER_NODE=/path/to/node`
- 无 Chrome：`apt install google-chrome-stable`（或 chromium），非标准路径则配 `CHROME_PATH=`
- **上线后第一件事：实测一份报告 PDF 下载**（用户报告页或 admin 预览），失败立刻看 `data/logs/` 与 tmux backend 日志中的渲染器报错

---

## 三、nginx 配置（容易漏的动作）

新增 `deploy/nginx-static-cache.conf`：`/assets/`、`/fonts/` 30 天 immutable 长缓存（修复此前每次刷新重下约 7.7MB 静态资源的问题）。

生产操作（参考 `wiki/开发文档/0705-nginx-prod.md` 的配置位置）：

```nginx
# 在 server 块中、location / 之前 include：
include /path/to/deploy/nginx-static-cache.conf;
```

```bash
nginx -t && nginx -s reload   # 1Panel OpenResty 容器：docker exec <容器名> nginx -s reload
```

**配套纪律**：`public/` 下资源引用必须带 `?v=yyyymmdd` 版本号，更新资源时递增版本号击穿缓存（next.config.js 的 headers() 只是直连 Next 时的兜底，两层口径一致）。此项不改不影响功能，仅损失性能。

---

## 四、上线步骤（按序执行）

```bash
# 0. 备份（虽无迁移，惯例）
pg_dump / cp 数据库文件

# 1. 拉代码（含 dist 渲染产物）
cd /home/gitclone/BeingDoing && git fetch && git checkout newui && git pull

# 2. 环境变量核对（见第一节，正常情况零改动）
#    重点确认 .env 与仓库版本同步（LLM_TURN_LOG_* 两行、NEXT_SERVER_ACTIONS_ENCRYPTION_KEY）

# 3. 运行时检查（见第二节：node ≥20 + Chrome）

# 4. 重启（生产模式：清 .next 重新 build + start）
./start.sh start-run        # 等同 ./start.sh prod

# 5. nginx 静态缓存片段 include + reload（见第三节）

# 6. 冒烟验证（见第五节清单）
```

---

## 五、冒烟验证清单

| # | 项目 | 操作 | 预期 |
|---|---|---|---|
| 1 | 登录 | 普通用户登录 | 新版 UI 正常渲染 |
| 2 | 探索流程 | 进入任一阶段对话 | 对话、选择矩阵、结论卡正常 |
| 3 | 沉淀 guided 布局 | rumination 页 | 「新建组合」按钮可见；已提交终选的账号按钮**置灰不消失**（本次修复项） |
| 4 | **报告 PDF（xunlu 首切）** | 用户报告页下载 / admin 预览 | PDF 正常生成下载，视觉为 xunlu 设计版 |
| 5 | 报告页三态 | ready / error / none 各验一份 | none 分支有「生成报告」+「申请复核」双按钮（本次修复项） |
| 6 | admin 外观配置 | /admin/appearance | 中文名 + 色块示意（本次修复项），保存后全局生效 |
| 7 | admin 轮次诊断 | super_admin 进入 | 能查询 llm_turns 日志 |
| 8 | 静态缓存 | 刷新页面看 Network | /assets/、/fonts/ 返回 `cache-control: public, max-age=2592000, immutable` |
| 9 | 定时任务 | backend 启动日志 | APScheduler 注册 LLM 轮次清理 job（cron 0 5 * * *） |
| 10 | 邮件 | 触发一封（如验证码） | 落款带「系统发送邮箱不接收回复」注脚 |

---

## 六、回滚预案

- **整体回滚**：`git checkout b9bfd4f（或原生产 commit）&& ./start.sh start-run`。无数据库迁移，直接回退代码即可，数据零损失
- **仅 PDF 渲染故障**：优先排查 node/chrome 环境（第二节）；无法快速修复则整体回滚（RENDER_ENGINE 开关已删除，无法单独切回 weasyprint——这是 ADR-0021 的既定取舍）
- **nginx**：注释掉 include 行 + reload 即回退缓存策略，与代码无关

---

## 附：本次迁移"不需要做"的完整清单

- ❌ alembic 数据库迁移（无新版本）
- ❌ pip 依赖安装（requirements 零变化）
- ❌ 前端 npm install（package.json 零变化）
- ❌ report-renderer 的 npm install / build（dist 已入库）
- ❌ 卸载 weasyprint（export_service 仍在用）
- ❌ 新增任何必填环境变量（全部有默认值）
