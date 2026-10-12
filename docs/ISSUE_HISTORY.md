# GitHub历史条目索引

获取与核对日期：2026-10-12。来源为本轮通过 [GitHub issues API](https://api.github.com/repos/LYDONLUCIEN/BeingDoing/issues?state=all&per_page=100) 分页只读获取的条目和各条目的comments API。未修改在线issue、PR或评论。历史代码核对基线为`5b461e6`；本轮v3退役另见 [ADR-0025](adr/0025-retire-v3-runtime-and-separate-history.md)，完成情况见 [CHANGELOG](CHANGELOG.md)。

快照包含**103条：102个issue＋1个PR（#1）**，其中GitHub原状态14个open、89个closed（含PR）；共有114条issue评论。API的 `/issues` 列表会包含PR，所以不能称为103个独立issue。下面保留全部编号、原题、原状态、创建/更新日期和全部评论的精确来源链接；日期均为UTC，表格日期年份均为2026。快照最大更新时间为2026-10-08，此日期不代表之后线上没有变化。

GitHub状态是当时的工作流状态，研究判定是对现行适用范围的判断，两者独立。closed可能是完成记录、暂缓归档或本地未提交；open也可能已经入库但待部署/验收。题目中的“已修复/上线/待提交”保留原文，不能代替本轮核验。很多正文和评论标注AI生成的triage；它们是项目历史记录，仍需结合源码、提交及明确产品决定，不单独当作当前用户指令。

本索引完整覆盖条目和评论，但没有对每个旧缺陷重新复现。标为“历史记录/未复测”的条目不能推导当前仍有漏洞或已经安全。重点替代链已由 [HISTORY_EVIDENCE](HISTORY_EVIDENCE.md) 核对；不在索引复制正文、服务器细节、用户实例或密钥配置。

## 重点替代链

<a id="h1"></a>

- **H1：v3运行时退役**。旧Step3矩阵/3b和相关未关闭issue由本轮用户决定废止；v4 `combo_id`与历史读取另有语义。见 [历史证据第1节](HISTORY_EVIDENCE.md#1-v3-被废止的是什么v4-必须保留的是什么)和[ADR-0025](adr/0025-retire-v3-runtime-and-separate-history.md)。

<a id="h2"></a>

- **H2：结论卡与提示词**。#68去旧话术→ADR-0015用户手填v4卡；前四阶段#87的门槛→9月无轮数限制/手动先judge。两条链不可合并删除。见[历史证据第2–3节](HISTORY_EVIDENCE.md)。

<a id="h3"></a>

- **H3：身份、交付与授权**。#45沙箱归属→ADR-0010/0014→#100及ADR-0023/0024；购买者、激活人、运营标签和产品权益分开。见[历史证据第4–7、12节](HISTORY_EVIDENCE.md)。

<a id="h4"></a>

- **H4：价格与延期**。#67的128元有b123969实施证据；更晚ADR-0014的159元未查到实施或撤销，不能擅改价；20元90天延期已被ADR-0016替代。见[历史证据第5–6节](HISTORY_EVIDENCE.md)。

<a id="h5"></a>

- **H5：支付、券与退款**。#57服务端三层确认；#93券期限/owner→#101按行多次核销；早期整单不退→#102明细行退款审批。见[历史证据第8节](HISTORY_EVIDENCE.md)。

<a id="h6"></a>

- **H6：报告**。#54/77/88→ADR-0021唯一xunlu；#80复核发布；#83提交触发→#91固定24h；#89终选是报告内容权威。见[历史证据第9–10节](HISTORY_EVIDENCE.md)。

<a id="h7"></a>

- **H7：前端与兼容**。#55旧浮窗→0919/0923多轮UI；#90兼容回退；#95资源优化→ADR-0022/#103指定聊天范围静态皮肤。一次性不改支付/布局的限制不永久化。见[历史证据第14节](HISTORY_EVIDENCE.md)。

<a id="h8"></a>

- **H8：认证**。#81固定锁15分钟→b9bfd4f阶梯锁；#85刷新并发/UTC修复；#32验证JWT与#97跨标签页同步是不同故障。见[历史证据第13节](HISTORY_EVIDENCE.md)。

<a id="h9"></a>

- **H9：存储与迁移**。#17软归档/竞态修订；#58脚本交付不等于生产执行；#59明确暂缓；#53数据治理待评估，不自动清真实数据。见[历史证据第11节](HISTORY_EVIDENCE.md)。

## 全量条目与评论

评论按创建时间排序，链接文字为创建日期（UTC，2026）；同日多条以序号区分。零评论明确记为0。原题保持原意，Markdown转义仅用于表格显示。

| 编号/类型 | GitHub原状态 | 原始标题 | 创建→更新（UTC） | 本轮研究判定 | 评论来源 |
| --- | --- | --- | --- | --- | --- |
| #1 PR | closed | [Claude](https://github.com/LYDONLUCIEN/BeingDoing/pull/1) | 04-11→04-11 | API包含的PR；标题为Claude，正文为V2手动PR记录；closed不证明已合并，本轮未查PR merge状态。 | 0 |
| #2 issue | closed | [前端启动慢 + 页面内容加载不出来（Banner、他们的故事等）](https://github.com/LYDONLUCIEN/BeingDoing/issues/2) | 05-02→05-02 | 历史前端修复记录；本轮未逐项复测当时性能和加载问题。 | 1：[05-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/2#issuecomment-4363724246) |
| #3 issue | closed | [对话输入框在 AI 回复完成后失去焦点](https://github.com/LYDONLUCIEN/BeingDoing/issues/3) | 05-02→05-02 | 历史输入焦点修复；本轮未逐项复测。 | 1：[05-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/3#issuecomment-4363859936) |
| #4 issue | closed | [删除 thread 后后端数据未同步删除，导致历史数据残留](https://github.com/LYDONLUCIEN/BeingDoing/issues/4) | 05-02→05-02 | 历史thread删除问题；后续软归档/防幽灵恢复见#17，不能直接沿用硬删方案。 | 2：[05-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/4#issuecomment-4364014464) · [05-02-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/4#issuecomment-4364014687) |
| #5 issue | closed | [Thread 内出现重复的 AI 引导语](https://github.com/LYDONLUCIEN/BeingDoing/issues/5) | 05-02→05-02 | 历史引导语去重记录；本轮未逐项复测。 | 3：[05-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/5#issuecomment-4364015773) · [05-02-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/5#issuecomment-4364079727) · [05-02-3](https://github.com/LYDONLUCIEN/BeingDoing/issues/5#issuecomment-4364079767) |
| #6 issue | closed | [切换阶段后莫名创建新 thread](https://github.com/LYDONLUCIEN/BeingDoing/issues/6) | 05-02→05-02 | 历史阶段/thread恢复记录；本轮未逐项复测。 | 2：[05-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/6#issuecomment-4364015848) · [05-02-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/6#issuecomment-4364079843) |
| #7 issue | closed | [Fix: Rumination 假设悬停预览定位错误 + 滚动条失效](https://github.com/LYDONLUCIEN/BeingDoing/issues/7) | 05-03→05-03 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-03-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/7#issuecomment-4366335208) |
| #8 issue | closed | [Rumination 深度讨论流程级联 Bug：filter_step 污染、回看模式误判、重新填写失效、neg_gate 不重触发](https://github.com/LYDONLUCIEN/BeingDoing/issues/8) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/8#issuecomment-4367703568) · [05-04-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/8#issuecomment-4367759168) |
| #9 issue | closed | [Bug: Step 3 假设确认列跳过前端验证，未填写行无抖动提示](https://github.com/LYDONLUCIEN/BeingDoing/issues/9) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/9#issuecomment-4368207301) |
| #10 issue | closed | [Bug: Step 3 深度讨论后右侧对话框不显示引导语](https://github.com/LYDONLUCIEN/BeingDoing/issues/10) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/10#issuecomment-4368207585) |
| #11 issue | closed | [Bug: Step 3 选择「无」的行未被纳入深度讨论](https://github.com/LYDONLUCIEN/BeingDoing/issues/11) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/11#issuecomment-4368207846) |
| #12 issue | closed | [Bug: 结束深度讨论后再次提交仍弹出闸门弹窗](https://github.com/LYDONLUCIEN/BeingDoing/issues/12) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/12#issuecomment-4368242888) |
| #13 issue | closed | [Bug: Early termination 跳转 step7 时当前步骤 submitted 快照被清除导致步骤未锁定](https://github.com/LYDONLUCIEN/BeingDoing/issues/13) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/13#issuecomment-4368522889) |
| #14 issue | closed | [Bug: 深度讨论期间表格行选中状态残留且无法取消](https://github.com/LYDONLUCIEN/BeingDoing/issues/14) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/14#issuecomment-4368632030) |
| #15 issue | closed | [fix: rumination 短链跳过的子步未被锁定，用户仍可查看和提交](https://github.com/LYDONLUCIEN/BeingDoing/issues/15) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/15#issuecomment-4369729116) |
| #16 issue | closed | [feat: step1/2/3 过滤后 0 条时弹窗 + LLM 双通道沟通兜底](https://github.com/LYDONLUCIEN/BeingDoing/issues/16) | 05-04→05-04 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[05-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/16#issuecomment-4370149780) · [05-04-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/16#issuecomment-4370297561) |
| #17 issue | closed | [\[P0\] R5-21-01: 多对话删除软归档 + 禁止幽灵恢复](https://github.com/LYDONLUCIEN/BeingDoing/issues/17) | 05-21→05-23 | 软归档原则及后续竞态修复；最新评论已修正初版前端按remaining_thread_ids过滤方案。见[H9](#h9)。 | 2：[05-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/17#issuecomment-4506547338) · [05-23-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/17#issuecomment-4525687328) |
| #18 issue | open | [\[P1\] R5-21-05~10: Rumination step3 行解锁 + 引导文案](https://github.com/LYDONLUCIEN/BeingDoing/issues/18) | 05-21→06-05 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[05-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/18#issuecomment-4506636095) · [06-05-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/18#issuecomment-4627298361) |
| #19 issue | open | [\[P1\] R5-21-08: neg_gate current_index 逐条深度讨论](https://github.com/LYDONLUCIEN/BeingDoing/issues/19) | 05-21→05-21 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[05-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/19#issuecomment-4507541384) |
| #20 issue | closed | [修复：新用户无激活码时无法保存个人简介](https://github.com/LYDONLUCIEN/BeingDoing/issues/20) | 06-02→06-02 | 历史无码保存简介修复；与当前试用/邮箱验证门槛分开核对。 | 1：[06-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/20#issuecomment-4597941958) |
| #21 issue | closed | [修复：重新登录后应回到触发登录的页面而非 /explore/intro](https://github.com/LYDONLUCIEN/BeingDoing/issues/21) | 06-02→06-02 | 历史登录后返回路径修复；未独立复测。 | 0 |
| #22 issue | closed | [前端 Markdown 渲染：中文标点紧邻加粗/斜体标记时渲染失败](https://github.com/LYDONLUCIEN/BeingDoing/issues/22) | 06-02→06-04 | 历史Markdown渲染修复；当前仍需遵守SafeMarkdownPreview安全边界，旧实现不作安全保证。 | 2：[06-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/22#issuecomment-4598103977) · [06-04-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/22#issuecomment-4621287027) |
| #23 issue | open | [Rumination Step3: 用户跳过所有行后的对话引导逻辑优化](https://github.com/LYDONLUCIEN/BeingDoing/issues/23) | 06-03→06-03 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 0 |
| #24 issue | closed | [rumination step1 AI跑偏：强化范围锁定与流程引导](https://github.com/LYDONLUCIEN/BeingDoing/issues/24) | 06-03→06-03 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-03-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/24#issuecomment-4612956708) |
| #25 issue | closed | [Step2 不匹配闸门（neg gate）在重新填写后未触发](https://github.com/LYDONLUCIEN/BeingDoing/issues/25) | 06-03→06-03 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-03-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/25#issuecomment-4613104470) |
| #26 issue | closed | [重构：Step3 表格操作改为对话消息机制](https://github.com/LYDONLUCIEN/BeingDoing/issues/26) | 06-05→06-05 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-05-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/26#issuecomment-4631732404) |
| #27 issue | closed | [Rumination Step3: Tag tooltip 样式、生成时机、点击行为三项 UX 改进](https://github.com/LYDONLUCIEN/BeingDoing/issues/27) | 06-05→07-02 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[07-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/27#issuecomment-4863885479) |
| #28 issue | closed | [\[P1\] Rumination Step5/6 Neg Gate 不触发 + label 字段名 bug](https://github.com/LYDONLUCIEN/BeingDoing/issues/28) | 06-05→07-02 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[07-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/28#issuecomment-4863882877) · [07-02-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/28#issuecomment-4863883088) |
| #29 issue | closed | [feat: 新增 Admin 用户管理页面](https://github.com/LYDONLUCIEN/BeingDoing/issues/29) | 06-08→06-08 | 用户管理初始实现；运营标签/筛选后来由#100、ADR-0023扩展，标签不等于权限。 | 1：[06-08-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/29#issuecomment-4645059809) |
| #30 issue | closed | [fix: email_verified 数据不同步 — AuthModal 缺少字段传递 + alembic 迁移修复](https://github.com/LYDONLUCIEN/BeingDoing/issues/30) | 06-09→06-09 | 邮箱验证字段同步历史修复；跨标签页问题另由#97处理。 | 1：[06-09-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/30#issuecomment-4660170175) |
| #31 issue | closed | [子步3：假设候选(hyp)兜底 retry、行号绑定与 chip 填表修复](https://github.com/LYDONLUCIEN/BeingDoing/issues/31) | 06-12→06-12 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[06-12-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/31#issuecomment-4688956749) · [06-12-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/31#issuecomment-4688956910) |
| #32 issue | closed | [邮箱验证链接点击后显示过期（JWT type 被覆盖为 access）](https://github.com/LYDONLUCIEN/BeingDoing/issues/32) | 06-16→06-16 | JWT用途被覆盖修复，对应8f8dbce；验证token不能当access token。见[H8](#h8)。 | 1：[06-16-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/32#issuecomment-4718654229) |
| #33 issue | closed | [后端 DEBUG 模式下 filelock 日志刷屏（已在 main.py 黑名单补齐修复）](https://github.com/LYDONLUCIEN/BeingDoing/issues/33) | 06-20→06-20 | 日志降噪修复记录；未复测，不推导应关闭全部锁相关日志。 | 1：[06-20-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/33#issuecomment-4756801333) |
| #34 issue | closed | [step2 选择不匹配后进入 step3 时 matrix 面板不渲染(死锁)](https://github.com/LYDONLUCIEN/BeingDoing/issues/34) | 06-20→06-20 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-20-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/34#issuecomment-4756993808) |
| #35 issue | closed | [Step3 矩阵：切换热爱自动选默认优势 + 后端富 meta 数据](https://github.com/LYDONLUCIEN/BeingDoing/issues/35) | 06-20→06-20 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-20-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/35#issuecomment-4756994684) |
| #36 issue | closed | [\[P2\] Rumination Step3: 完成弹窗「不再提示」勾选即生效](https://github.com/LYDONLUCIEN/BeingDoing/issues/36) | 06-21→06-21 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/36#issuecomment-4761316110) |
| #37 issue | closed | [Rumination step3b: 表格行解锁 / 选中保持 / chips 稳定生成 / 选中行联动 neg gate / 当前假设喂给模型](https://github.com/LYDONLUCIEN/BeingDoing/issues/37) | 06-22→06-22 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-22-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/37#issuecomment-4766995237) |
| #38 issue | closed | [rumination step3 matrix → discussion 模式切换 + 3b 交互 + chips 生成一系列问题修复](https://github.com/LYDONLUCIEN/BeingDoing/issues/38) | 06-22→06-22 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[06-22-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/38#issuecomment-4767051560) · [06-22-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/38#issuecomment-4767053270) |
| #39 issue | closed | [fix(rumination): discussion 选行发消息后输入框被禁用](https://github.com/LYDONLUCIEN/BeingDoing/issues/39) | 06-24→06-24 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-24-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/39#issuecomment-4786230369) |
| #40 issue | closed | [feat: 用户信息收集页(survey)新增隐私声明弹窗](https://github.com/LYDONLUCIEN/BeingDoing/issues/40) | 06-24→06-24 | 问卷隐私弹窗的历史产品记录；不是具体数据用途均合规的审计结论。 | 1：[06-24-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/40#issuecomment-4786237638) |
| #41 issue | open | [rumination step3 重新填写后 discussion 模式引导语错乱 + 历史消息清不干净](https://github.com/LYDONLUCIEN/BeingDoing/issues/41) | 06-24→06-24 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[06-24-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/41#issuecomment-4786263966) |
| #42 issue | closed | [fix(rumination): step3 discussion 引导语错误 & step2 重新填写重复引导语](https://github.com/LYDONLUCIEN/BeingDoing/issues/42) | 06-26→06-26 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[06-26-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/42#issuecomment-4807982730) · [06-26-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/42#issuecomment-4807982919) |
| #43 issue | closed | [Rumination 表格导出 + admin 详情按 step 展示(含 combo 分组)](https://github.com/LYDONLUCIEN/BeingDoing/issues/43) | 07-02→07-02 | 旧v3表格/按combo导出；现行执行退役，历史读取/导出边界另见ADR-0025。见[H1](#h1)。 | 1：[07-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/43#issuecomment-4863705166) |
| #44 issue | closed | [fix(rumination): 表格内「自定义」输入框删空文字即失焦](https://github.com/LYDONLUCIEN/BeingDoing/issues/44) | 07-02→07-02 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 2：[07-02-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/44#issuecomment-4863703368) · [07-02-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/44#issuecomment-4863703607) |
| #45 issue | closed | [feat: 激活码归属隔离 + 迁移功能 + 孤儿 report 清理脚本](https://github.com/LYDONLUCIEN/BeingDoing/issues/45) | 07-03→07-03 | 真实码与admin沙箱隔离/归属迁移来源；跨JSON原子性仍需实现验证。见[H3](#h3)。 | 1：[07-03-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/45#issuecomment-4872315051) |
| #46 issue | closed | [fix(rumination): combo matrix → step3b 表行 id 污染修复 + 数据修正 + admin 展示优化](https://github.com/LYDONLUCIEN/BeingDoing/issues/46) | 07-03→07-03 | 旧v3专属流程/问题；本轮已决定退役，不能因旧issue恢复运行时。见[H1](#h1)。 | 1：[07-03-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/46#issuecomment-4875266025) |
| #47 issue | closed | [fix(ui): 报告导出标题中残留的「寻录」替换为「寻路」](https://github.com/LYDONLUCIEN/BeingDoing/issues/47) | 07-04→07-04 | 旧品牌标题修复；后续ADR-0012统一新品牌，内部母版名称不因此强改。 | 1：[07-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/47#issuecomment-4881270869) |
| #48 issue | closed | [对话统计脚本增强：过滤能力 + 聚合报表 + rumination 子 step 时长](https://github.com/LYDONLUCIEN/BeingDoing/issues/48) | 07-04→07-04 | 历史统计脚本增强；v3子步含义只解释历史，未逐项核验脚本现行范围。 | 1：[07-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/48#issuecomment-4881769347) |
| #49 issue | closed | [fix(site-notices): admin 列表为空 + banner 被 TopNavbar 遮挡](https://github.com/LYDONLUCIEN/BeingDoing/issues/49) | 07-04→07-04 | 公告列表与层级修复记录；未逐项复测。 | 1：[07-04-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/49#issuecomment-4882421635) |
| #50 issue | closed | [\[Bug\] 维护模式: admin 页面按钮触发后 nginx 拦截不生效, 仅 CLI 模式工作](https://github.com/LYDONLUCIEN/BeingDoing/issues/50) | 07-04→07-05 | 维护模式故障修复记录；不证明现部署配置仍相同。 | 1：[07-05-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/50#issuecomment-4884934820) |
| #51 issue | open | [维护模式: dev/prod 环境配置分离 + 容器名自动探测](https://github.com/LYDONLUCIEN/BeingDoing/issues/51) | 07-05→07-05 | 维护环境分离/容器识别仍为open提案；未找到本轮实施证据，不执行旧运维步骤。 | 0 |
| #52 issue | closed | [生产环境 IMAP 退信扫描配置问题（已修复）](https://github.com/LYDONLUCIEN/BeingDoing/issues/52) | 07-05→07-05 | IMAP环境故障记录；不复用旧账号配置，不证明当前邮件链路已验收。 | 1：[07-05-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/52#issuecomment-4885215379) |
| #53 issue | open | [v1.5 部署后数据治理: report 线程一致性 + rebuild_report_lineage 报错排查](https://github.com/LYDONLUCIEN/BeingDoing/issues/53) | 07-05→07-05 | 数据治理待评估；曾记录缺失/孤儿thread，未获批量清数据授权。见[H9](#h9)。 | 1：[07-05-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/53#issuecomment-4885326317) |
| #54 issue | closed | [PDF 报告生成功能：LLM 叙事报告 + 水印 + 异步下载](https://github.com/LYDONLUCIEN/BeingDoing/issues/54) | 07-15→07-15 | 早期LLM报告/PDF实现；后被ADR-0017/0019/0021扩展和替代，非当前引擎规范。见[H6](#h6)。 | 1：[07-15-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/54#issuecomment-4979063265) |
| #55 issue | closed | [反馈浮窗改造：书签式抽拉入口（圆角矩形标签 + 悬停展开功能描述）](https://github.com/LYDONLUCIEN/BeingDoing/issues/55) | 07-21→07-21 | 旧反馈浮窗形态；0919站内信/反馈抽屉迁移后不能要求保留旧拖拽书签。见[H7](#h7)。 | 1：[07-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/55#issuecomment-5031813916) |
| #56 issue | closed | [双域名并存支持：beyondego.me 与 soulhappylab.com 同时可用（含 301 死循环修复）](https://github.com/LYDONLUCIEN/BeingDoing/issues/56) | 07-23→07-23 | 双域名并行迁移的历史记录；后续品牌/域名收敛改变范围，不是永久双域兼容命令。 | 1：[07-23-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/56#issuecomment-5057654725) |
| #57 issue | closed | [支付宝电脑网站支付（page.pay）上线 + 激活码「未激活首用起算」+ 商品文案改版（2026-07-25）](https://github.com/LYDONLUCIEN/BeingDoing/issues/57) | 07-25→07-25 | page.pay及服务端三层确认已落地；首用起算/自动升级/旧弹窗形态被后续规则替代。见[H3](#h3)、[H5](#h5)。 | 1：[07-25-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/57#issuecomment-5078425115) |
| #58 issue | closed | [ADR-0008 存量激活码 schema 迁移：一次性补全脚本 + 运维文档](https://github.com/LYDONLUCIEN/BeingDoing/issues/58) | 07-26→07-26 | 旧激活码schema脚本交付记录；关闭评论仍留生产执行待办，不能据closed认定已迁。见[H9](#h9)。 | 1：[07-26-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/58#issuecomment-5082487690) |
| #59 issue | closed | [存储迁移：JSON 文件数据全量入 SQLite，条件触发 PostgreSQL（暂缓，待 v1.6.0 后启动）](https://github.com/LYDONLUCIEN/BeingDoing/issues/59) | 07-26→07-26 | 明确暂缓的存储演进计划；closed是留档，JSON仍在运行，非已完成迁移。见[H9](#h9)。 | 1：[07-26-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/59#issuecomment-5082560687) |
| #60 issue | closed | [rumination v4: &lt;&lt;CONCLUSION_READY&gt;&gt; 标记与 tool JSON 泄漏到聊天气泡](https://github.com/LYDONLUCIEN/BeingDoing/issues/60) | 07-27→07-27 | 早期v4自动出卡协议泄漏；相关chips/tool/双信号已被ADR-0015删除。见[H2](#h2)。 | 1：[07-27-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/60#issuecomment-5088637326) |
| #61 issue | closed | [rumination v4: 出卡即锁死对话 —— 改为出卡不锁/确认才锁/「再聊聊」](https://github.com/LYDONLUCIEN/BeingDoing/issues/61) | 07-27→07-27 | 早期v4出卡/确认/再聊聊边界；用户主导卡和判定生命周期以后续ADR-0015为准。见[H2](#h2)。 | 1：[07-27-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/61#issuecomment-5088637632) |
| #62 issue | closed | [rumination v4 终选弹窗：不推荐的理由不可见、完整假设看不到](https://github.com/LYDONLUCIEN/BeingDoing/issues/62) | 07-27→07-27 | v4终选信息可见性历史修复；当前终选仍需保留假设与不推荐理由，旧样式非强制。 | 1：[07-27-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/62#issuecomment-5088637997) |
| #63 issue | closed | [rumination v4: AI 零可见文本回复导致空气泡（多层兜底缺失）](https://github.com/LYDONLUCIEN/BeingDoing/issues/63) | 07-27→07-27 | v4空回复历史修复；旧出卡兜底与当前纯咨询链分开，不恢复已删除协议。见[H2](#h2)。 | 1：[07-27-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/63#issuecomment-5088638347) |
| #64 issue | closed | [rumination v4: 「结论卡生成中」指示在卡生成后残留不消失](https://github.com/LYDONLUCIEN/BeingDoing/issues/64) | 07-27→07-27 | 早期v4自动出卡loading修复；相关自动写卡路径已由ADR-0015替代。见[H2](#h2)。 | 1：[07-27-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/64#issuecomment-5088638711) |
| #65 issue | closed | [验证邮件中的链接为纯文本，部分邮箱客户端无法点击](https://github.com/LYDONLUCIEN/BeingDoing/issues/65) | 07-28→07-28 | 验证邮件链接格式修复记录；生产邮件可用性未在本轮验证。 | 2：[07-28-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/65#issuecomment-5103745884) · [07-28-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/65#issuecomment-5103746078) |
| #66 issue | closed | [rumination v4 终选弹窗：统一紫色主题，简化卡片差异](https://github.com/LYDONLUCIEN/BeingDoing/issues/66) | 07-28→07-28 | 旧终选紫色视觉记录；后续0919/0923及ADR-0022须一并核对。见[H7](#h7)。 | 2：[07-28-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/66#issuecomment-5103749222) · [07-28-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/66#issuecomment-5103749756) |
| #67 issue | closed | [支付文案调整：套餐改名/年度调价 ¥128/延期统一 ¥20·3个月 + 首页对比表](https://github.com/LYDONLUCIEN/BeingDoing/issues/67) | 07-28→07-28 | 99→128已由b123969实施；延期20元90天被ADR-0016替代；后续159元决定未查到代码落地。见[H4](#h4)。 | 2：[07-28-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/67#issuecomment-5103750243) · [07-28-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/67#issuecomment-5103750851) |
| #68 issue | closed | [Rumination v4 提示词对齐原生 md 文档（去除 v3 旧逻辑污染）](https://github.com/LYDONLUCIEN/BeingDoing/issues/68) | 07-28→07-28 | 去v3话术污染原则保留；当时chips/tool工程协议已被ADR-0015替代。见[H2](#h2)。 | 1：[07-28-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/68#issuecomment-5103750298) |
| #69 issue | closed | [\[记录\] 激活页：新用户自动预填试用激活码 + 找回引导文案](https://github.com/LYDONLUCIEN/BeingDoing/issues/69) | 07-28→07-28 | 激活页预填/找回引导历史修复；发试用码时点按当前邮箱验证规则，不照抄早期注册即送。 | 1：[07-28-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/69#issuecomment-5104070564) |
| #70 issue | closed | [【故障记录】支付宝 page.pay 支付失败：invalid-signature 验签出错（已解决）](https://github.com/LYDONLUCIEN/BeingDoing/issues/70) | 08-05→08-05 | 渠道验签配置故障记录；不复制旧密钥配置，不证明当前渠道已经联调。 | 1：[08-05-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/70#issuecomment-5186533500) |
| #71 issue | closed | [\[已修复\] 验证邮件链接输出 localhost：FRONTEND_URL 配置链路与 start.sh 环境管理缺陷复盘](https://github.com/LYDONLUCIEN/BeingDoing/issues/71) | 08-05→08-05 | 邮件外链与环境加载故障来源；实际FRONTEND_URL需当前环境确认。 | 1：[08-05-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/71#issuecomment-5188323311) |
| #72 issue | closed | [Rumination v4 对话气泡缺少头像与思考占位动画](https://github.com/LYDONLUCIEN/BeingDoing/issues/72) | 08-07→08-07 | v4头像/思考占位历史修复；功能反馈不同于ADR-0022禁止的装饰动画。 | 1：[08-07-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/72#issuecomment-5215009779) |
| #73 issue | closed | [已注销账户登录后恢复页闪退，收不到恢复验证码邮件](https://github.com/LYDONLUCIEN/BeingDoing/issues/73) | 08-08→08-08 | 注销恢复链路历史修复；未逐项复测恢复邮件和跳转。 | 1：[08-08-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/73#issuecomment-5225767513) |
| #74 issue | closed | [Rumination v4 首次进入开场弹窗（每激活码一次）](https://github.com/LYDONLUCIEN/BeingDoing/issues/74) | 08-10→08-10 | v4开场弹窗按探索记录持久化intro_shown，基线存在；不恢复旧AB运行时。 | 1：[08-10-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/74#issuecomment-5242658858) |
| #75 issue | closed | [购买年度套餐（3人团队码）后提示团队分析报告申请方式](https://github.com/LYDONLUCIEN/BeingDoing/issues/75) | 08-10→08-10 | 年度套餐团队分析联系入口记录；不能推断团队分析完整功能已开放。 | 1：[08-10-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/75#issuecomment-5242660879) |
| #76 issue | closed | [首页方案对比表优化：空值填充 `-`、新增「7 天免费延期」行、「最受欢迎」改为季度套餐](https://github.com/LYDONLUCIEN/BeingDoing/issues/76) | 08-10→08-10 | 首页对比表旧文案调整；免费延期看ADR-0016，当前价格另见H4。 | 1：[08-10-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/76#issuecomment-5242674997) |
| #77 issue | closed | [报告 PDF 大改版：总览预览页 + 配色可配置 + 表格/标题/列表/分页/信件质量修复（ADR-0017）](https://github.com/LYDONLUCIEN/BeingDoing/issues/77) | 08-12→08-15 | 报告后处理/旧配色配置来源；双引擎开关及旧CSS由ADR-0021替代。见[H6](#h6)。 | 2：[08-12-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/77#issuecomment-5265130776) · [08-15-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/77#issuecomment-5301067408) |
| #78 issue | closed | [402 试用拦截弹窗：按用户持码状态分级引导（has_upgrade_codes）](https://github.com/LYDONLUCIEN/BeingDoing/issues/78) | 08-12→08-12 | 试用402分级引导记录；has_upgrade_codes表示可升级码情况，不是付费/权限同义词。 | 1：[08-12-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/78#issuecomment-5265142153) |
| #79 issue | closed | [Rumination v4 终选 n选3 UI 对齐设计稿 nto3.png（卡片结构 + 假设缩略悬停）](https://github.com/LYDONLUCIEN/BeingDoing/issues/79) | 08-12→08-12 | v4终选N选3设计参考；1–3方向业务与后来视觉换肤应分开。见[H2](#h2)、[H7](#h7)。 | 1：[08-12-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/79#issuecomment-5265143560) |
| #80 issue | closed | [报告复核体系：用户重新生成下线，改为「申请复核 + admin 确认发布」流程](https://github.com/LYDONLUCIEN/BeingDoing/issues/80) | 08-19→08-19 | 复核＋staging＋发布已落地a5a96ad；后端受权force明确保留，失败重试不等于内容重生成。见[H6](#h6)。 | 1：[08-19-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/80#issuecomment-5336429701) |
| #81 issue | closed | [登录防爆破：失败计数锁定 + 统一错误提示（已实现）](https://github.com/LYDONLUCIEN/BeingDoing/issues/81) | 08-21→08-21 | 初版5次锁15分钟已被b9bfd4f阶梯锁替代；进程内边界仍在。见[H8](#h8)。 | 1：[08-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/81#issuecomment-5372795415) |
| #82 issue | closed | [修复：AI 回复截断/重复 与 rumination_v4 结论卡判定 JSONDecodeError](https://github.com/LYDONLUCIEN/BeingDoing/issues/82) | 08-21→08-23 | 模型截断/JSON错误历史修复；参数与模型场景已继续演进，不把旧额度一律写成当前。 | 2：[08-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/82#issuecomment-5372812846) · [08-23-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/82#issuecomment-5386659523) |
| #83 issue | closed | [提交即审核：rumination v4 终选提交触发审核计时+报告预生成，下载/异常态收口](https://github.com/LYDONLUCIEN/BeingDoing/issues/83) | 08-23→08-23 | v4终选提交即审核/预生成已落地349c40d；随机时限后来由#91替代。见[H6](#h6)。 | 0 |
| #84 issue | closed | [全部场景统一 deepseek-v4-pro + 思维链，max_tokens 小额度集中排雷（合并 #82 同类问题）](https://github.com/LYDONLUCIEN/BeingDoing/issues/84) | 08-23→08-23 | 当时全场景pro＋思维链记录；后来conclusion场景独立配置，不能当永久模型锁定。 | 1：[08-23-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/84#issuecomment-5386659351) |
| #85 issue | closed | [用户持续使用约 1 小时被踢出登录：refresh token 机制失效（SQLite 比较 500 + 并发重放误杀整族）](https://github.com/LYDONLUCIEN/BeingDoing/issues/85) | 08-25→08-25 | refresh时间与并发误杀由def325a修复；关闭评论曾注明未提交，Git证据补足。见[H8](#h8)。 | 1：[08-25-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/85#issuecomment-5404863126) |
| #86 issue | closed | [对话气泡头像与气泡间距收紧（视觉归属修复）+ rumination 结论卡移除选中优势徽章](https://github.com/LYDONLUCIEN/BeingDoing/issues/86) | 08-25→08-25 | 间距/徽章旧视觉调整；当前以末次设计决定为准，未独立复测。 | 0 |
| #87 issue | closed | [结论卡不出卡根治：≤10轮门控 + 手动出卡按钮（附 3 月以来全链路改动链条）](https://github.com/LYDONLUCIEN/BeingDoing/issues/87) | 08-25→08-26 | 11轮门槛/点击直接生成已被1a98a71和a513961替代；当前手动先judge。见[H2](#h2)。 | 4：[08-25-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/87#issuecomment-5407410103) · [08-26-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/87#issuecomment-5423609778) · [08-26-3](https://github.com/LYDONLUCIEN/BeingDoing/issues/87#issuecomment-5424770456) · [08-26-4](https://github.com/LYDONLUCIEN/BeingDoing/issues/87#issuecomment-5424933322) |
| #88 issue | closed | [报告 PDF 排版修复：xunlu 同页断表/断段（rebalance 合并）+ 分页估算常数校准 + 热爱章限定结论卡 keywords](https://github.com/LYDONLUCIEN/BeingDoing/issues/88) | 09-01→09-01 | xunlu分页和热爱数据范围修复记录；不能把旧估算常数替代现行渲染代码。见[H6](#h6)。 | 1：[09-01-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/88#issuecomment-5489602312) |
| #89 issue | closed | [\[决策记录\] 报告生成 prompt：rumination N选3 终选结论硬约束 + 平衡点判定注入](https://github.com/LYDONLUCIEN/BeingDoing/issues/89) | 09-06→09-06 | 终选原文＋平衡判定作为报告权威输入；仅新生成/复核新稿生效，不改旧缓存。见[H6](#h6)。 | 1：[09-06-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/89#issuecomment-5558758160) |
| #90 issue | closed | [【决策日志】旧内核浏览器（搜狗等）rumination 布局错乱、「完成并继续」不可点（已修复，ADR-0020）](https://github.com/LYDONLUCIEN/BeingDoing/issues/90) | 09-06→09-06 | ADR-0020兼容底线已落地；旧v3/AB表述已过时，IE仅静态提示。见[H7](#h7)。 | 1：[09-06-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/90#issuecomment-5558758363) |
| #91 issue | closed | [报告审核机制改造：随机 3~24h → 统一固定 24h（含生成看门狗）](https://github.com/LYDONLUCIEN/BeingDoing/issues/91) | 09-06→09-06 | 固定24h和看门狗由7a48de7落地；不重算旧pending，不是生成永不失败保证。见[H6](#h6)。 | 1：[09-06-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/91#issuecomment-5558759399) |
| #92 issue | closed | [首页新增「参考文献」一页纸模块（实现记录）](https://github.com/LYDONLUCIEN/BeingDoing/issues/92) | 09-15→09-15 | 首页参考文献模块历史实施记录；未独立核验引用内容或当前布局。 | 1：[09-15-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/92#issuecomment-5679680842) |
| #93 issue | closed | [折扣券有效期 + 用户绑定体系（020 迁移）实施记录与生产迁移事故复盘](https://github.com/LYDONLUCIEN/BeingDoing/issues/93) | 09-15→09-15 | 券期限/owner/迁移020来源；一次券核销和退款规则继续由#101/#102扩展，closed非部署证明。见[H5](#h5)。 | 1：[09-15-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/93#issuecomment-5679860475) |
| #94 issue | closed | [\[已修复\] 主聊天流空回复被静默吞掉：flash 只吐思维链、content 为空（用户体感「问了没回，再问才回」）](https://github.com/LYDONLUCIEN/BeingDoing/issues/94) | 09-21→09-21 | 空回复可观测性/重试修复记录；本轮未复测外部模型行为。 | 1：[09-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/94#issuecomment-5760400539) |
| #95 issue | open | [首页性能优化：静态资源缓存 + 图片压缩（主体已完成，跟踪遗留项）](https://github.com/LYDONLUCIEN/BeingDoing/issues/95) | 09-21→09-21 | open仍跟踪缓存部署/字体后续项；fcedbd1主体实施记录不证明所有遗留项完成。见[H7](#h7)。 | 1：[09-21-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/95#issuecomment-5761158700) |
| #96 issue | closed | [\[已修复\] 邮箱验证邮件发送失败：163 授权码失效致 550 认证被拒，错误分类误报为收件人拒收](https://github.com/LYDONLUCIEN/BeingDoing/issues/96) | 09-27→09-27 | 邮件供应商配置事故与错误分类记录；不复制授权凭据，不确认当前SMTP可用。 | 2：[09-27-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/96#issuecomment-5856595880) · [09-27-2](https://github.com/LYDONLUCIEN/BeingDoing/issues/96#issuecomment-5856596109) |
| #97 issue | open | [邮箱验证「已验证成功但原页面仍提示未验证」——前端 store 快照不跨标签页同步（已修复，待提交部署）](https://github.com/LYDONLUCIEN/BeingDoing/issues/97) | 10-04→10-04 | issue仍open/待提交，但代码已有2d2b290；前端状态同步问题，不是邮箱点号问题。见[H8](#h8)。 | 0 |
| #98 issue | open | [支付弹窗：二维码区域体验多轮优化后仍不符合预期（待补充具体症状）](https://github.com/LYDONLUCIEN/BeingDoing/issues/98) | 10-07→10-07 | open且具体体验/环境待核实；多轮支付二维码改动不能替代用户最终验收。 | 1：[10-07-1](https://github.com/LYDONLUCIEN/BeingDoing/issues/98#issuecomment-6040360688) |
| #99 issue | open | [\[已修复待提交部署\] 用户气泡出现协议 JSON：flash 漏写 \[/STATE_JSON\]，未闭合块被当正文落盘并经 done.response 盖回气泡](https://github.com/LYDONLUCIEN/BeingDoing/issues/99) | 10-08→10-08 | 协议JSON可见泄漏修复记录；open标题含待提交，不能仅凭标题判定当前代码或生产状态。 | 0 |
| #100 issue | open | [功能记录：admin 用户类型标签 + 按用户全量数据导出（已实现，待生产部署）](https://github.com/LYDONLUCIEN/BeingDoing/issues/100) | 10-08→10-08 | 运营标签/导出已入1774736，后有ADR-0023注册表；user_type=admin不授予管理员权限。见[H3](#h3)。 | 0 |
| #101 issue | open | [功能: 优惠券多次核销（促销码模式）+ 激活码/优惠券码格式区分 — 实施记录与上线待办](https://github.com/LYDONLUCIEN/BeingDoing/issues/101) | 10-08→10-08 | 四阶段代码提交已落地；issue仍列迁移024/生产发布待办。旧裸码兼容与按行核销保留。见[H5](#h5)。 | 0 |
| #102 issue | open | [功能记录：订单退款系统——全退/部分退统一申请单、按码分摊折算、admin 审批与全链路审计（已实现，待生产部署）](https://github.com/LYDONLUCIEN/BeingDoing/issues/102) | 10-08→10-08 | 退款四阶段代码已入main；issue仍列生产待办，不能把SQL＋JSON描述当原子性审计结论。见[H5](#h5)。 | 0 |
| #103 issue | open | [功能记录：chat/沉淀页静态皮肤视觉修复——三轮回调恢复「整页连续画布」+ 对话区贴线渐隐（已实现，待生产部署）](https://github.com/LYDONLUCIEN/BeingDoing/issues/103) | 10-08→10-08 | 多轮视觉修复有bd8d66f/68d18f2记录，生产待办未核实；后轮验收替代初版色带方案。见[H7](#h7)。 | 0 |

## 快照校验

原始JSON位于本轮临时工作区，不纳入仓库；本文件是非敏感的可追溯索引。逐项检查编号1–103无遗漏/重复、PR标识、114条评论归属、链接与API字段完全一致，且每条issue的评论数与已读取评论数量相同。未发现快照更新时间晚于调查日。远端内容可能继续变化，重新研究时应重新读取API，不能把本文当实时看板。

- issues快照SHA-256：`ab9597de1a44875374bda48ec260bad4110c202c8919453211f16b01ceab2123`。
- comments快照SHA-256：`6c755e6ee41c693e2ba809056a5882853744857d08d1fdffbaf94539c51d4ddd`。
