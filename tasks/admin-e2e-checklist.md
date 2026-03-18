# Admin 端到端验收清单（E2E）

> 用途：上线前按链路逐项验收。  
> 原则：**先功能链路，再权限安全，再数据一致性**。  
> 验收口径：每项需有“操作步骤 + 预期结果”。

---

## A. 环境与入口

- [ ] `https://admin.soulhappylab.com/admin` 可稳定打开（非 404/503）
- [ ] admin 子域 `/api` 正确反代到后端（接口返回非网关错误）
- [ ] 主站 `career.soulhappylab.com` 功能未受影响
- [ ] `NEXT_PUBLIC_API_URL` 为空时，同域 `/api` 请求正常

---

## B. 权限与隔离

- [ ] 普通用户访问 `/admin` 显示无权限提示
- [ ] 普通用户请求 `/api/v1/admin/*` 返回 403
- [ ] super_admin 可访问全部 admin 页面与接口
- [ ] 激活码 A 被用户 A 首次绑定后，用户 B 无法继续使用（403）
- [ ] 已删除/停用激活码不可继续对话

---

## C. 激活码生命周期

- [ ] 批量创建激活码成功（数量/模式/有效期正确）
- [ ] 批量状态更新成功（active/expired/revoked）
- [ ] 删除激活码后主列表保留记录，状态为 `deleted`
- [ ] 删除后垃圾桶可见，且可恢复
- [ ] 恢复后状态回到 `active`
- [ ] 30 天清理策略可用（手动 purge 与自动清理均可验证）
- [ ] “从数据库同步激活码”可补齐缺失记录

---

## D. 报告主链路（report -> step -> session）

- [ ] 激活后可创建/绑定 `report_id`
- [ ] 报告含 5 步：`values/strengths/interests/purpose/rumination`
- [ ] 每个 step 可绑定多个 `session_id`
- [ ] 命名兼容映射生效（旧命名可归并到统一命名）
- [ ] `/admin/reports` 可看到列表、详情、JSON 下载
- [ ] “从激活码补齐报告”可将空列表补齐

---

## E. 对话与阶段

- [ ] `/admin/conversations` 可按 `report_id/step_id/session_id/activation_code/user_id` 检索
- [ ] 列表中会话 message 数量可见
- [ ] 点击会话详情可查看原始对话结构
- [ ] session 不存在时返回合理错误（404）

---

## F. Dashboard 与统计

- [ ] Dashboard 默认从 `data/static/admin_dashboard_overview.json` 读取
- [ ] 手动同步后会从 `/data` 重算并覆盖 static 缓存
- [ ] 卡片数据正确：用户数/访问数/报告数/今日激活码
- [ ] 漏斗数据正确：5 步数量与比例递减可解释
- [ ] token 统计可用：总量 + 分步骤
- [ ] 数据命名差异不会导致统计中断（兼容映射生效）

---

## G. 日志与调试

- [ ] `/admin/logs` 可按 session/dimension 查询 chat records
- [ ] 可查看 session detail
- [ ] 可按 `session_id + log_index` 查看 like detail
- [ ] 前端报错可通过浏览器控制台 + admin logs 联合定位

---

## H. 系统设置（视觉控制）

- [ ] `/admin/system` 能显示只读系统配置（脱敏）
- [ ] 可切换明暗模式
- [ ] 可切换效果 preset
- [ ] 可调整 light/dark 关键配色并即时生效
- [ ] 重置配色按钮可恢复默认

---

## I. 数据排查与运维

- [ ] `sync_simple_storage_alias.py --dry-run` 输出合理
- [ ] 执行后 `data/simple` 下出现 `激活码__session_id` 别名
- [ ] 别名不影响原有会话读写
- [ ] 回滚流程可执行（配置回滚 + 代码回滚）

---

## J. 发布前最终门禁

- [ ] 所有 P0 功能链路通过
- [ ] 所有 P0 安全项通过
- [ ] 无阻断级报错（500/403误判/权限穿透）
- [ ] 已更新任务文档（完成项/遗留项/风险项）
- [ ] 发布窗口与回滚负责人明确

---

## 本轮验收记录模板

```md
### [YYYY-MM-DD HH:mm] E2E 验收记录
- 验收范围：
- 通过项：
- 失败项：
- 失败根因：
- 处理动作：
- 复验结果：
- 是否可发布：
```

