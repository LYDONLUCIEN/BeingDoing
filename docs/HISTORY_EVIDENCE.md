# 历史决策与替代证据

调查日期：2026-10-12。历史代码核对基线：`clean@5b461e6`，上游发布基线 `main=v1.8.0=e6181d4`。下文“基线现行”均指 `5b461e6`，不是本轮清理完成后的工作树。本文是历史证据索引，供整理开发规则、术语和 ADR 使用；不是部署确认，也不是安全审计通过证明。

来源为本仓库 Git 历史、`docs/adr`、`wiki/历史开发记录`（原 `wiki/开发文档`）、`docs/历史文档`、`tasks`、版本迁移说明，以及本轮通过 GitHub API 只读获取的完整 issue 列表与评论快照。`/issues` API 共返回103条记录，包含102个issue和1个PR（#1），另有114条issue评论；全部条目见 [GitHub历史索引](ISSUE_HISTORY.md)。筛选了与下述主题直接相关的讨论，并用基线代码及后续提交核对。未读取服务器、真实 `data/`、`app.db` 或环境密钥；未执行历史运维命令。旧文档里的账号、主机、交易与用户实例不在此复制。

本轮与该历史基线的主要差别：用户明确撤销v3运行时兼容保留要求，正在清理v3接口、提示词、状态机及专属测试，并将历史读取/导出与可运行产品分开。下文保留“本轮废止”的目标和旧实现证据，不将未提交、未验收的工作提前写为成功。最终边界见 [ADR-0025](adr/0025-retire-v3-runtime-and-separate-history.md)，当前决定与完成记录分别见 [DECISIONS](DECISIONS.md)、[CHANGELOG](CHANGELOG.md)。本轮没有撤销旧裸码、会员预留、迁移追溯等其他明确保留条件。

## 证据与状态的读法

2026-10-13 补充：根目录的 7 份独有历史文档已归档，原文及各自适用范围见 [根目录索引](ROOT_FILES.md)。4 月全仓评审与 SimpleChat 评审保存当时的安全观察、模块拆分提案及后续已执行记录；metadata 记录保存字段迁移的限定范围；两份 V2 记录对进度跳转状态有差异，不能把其中一份的“完成”当作当前验收。早期功能快照和 4.28 清单含已退役规则，不再放在根目录充当开发入口。现行风险仍以 SECURITY_REVIEW 为入口；未重新验证的历史建议保留为线索，没有自动升级为需求，也没有被宣布解决。

- **现行且已落地**：基线源码与决策一致；不表示生产已经部署、迁移或验收。
- **已替代**：后续决定改变了旧语义，旧文档只解释历史。
- **有条件保留**：兼容、未开放产品、设计母版等有明确保留理由；条件和适用范围不能省略。
- **未落地／待核实**：只有计划、历史表述或与代码不一致，不得直接变成当前规则。
- **本轮废止**：2026-10-12 用户明确不再保留 v3 `combo_id` 及旧设计。该指示优先于基线 `AGENTS.md` 和早期文档的 v3 保留句；本文不冒充其代码删除已经完成。

最新的明确用户决定确定目标，当前代码证明实现事实，历史 ADR／issue 解释原因。三者不一致时分别记录，不能只选一份文件覆盖另两者。尤其 `closed` 可能表示留档、暂缓或本地完成：[#59 的关闭评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/59#issuecomment-5082560687)明确是暂缓；[#85 的关闭评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/85#issuecomment-5404863126)明确当时尚未提交。文档标题含 `v3/v4` 或 `tag1.6.0` 也不是部署证据，必须区分 SimpleChat 版本、沉淀版本和 Git tag。

## 现行／替代矩阵

| 主题 | 过去做法 → 变更原因 | 基线现行决定或本轮目标 | 状态与约束类型 | 主要替代证据 |
|---|---|---|---|---|
| 沉淀 v3 矩阵 | 顺序逐行讨论 → 3×5 矩阵独立对话，随后公共 3b 深聊 | 本轮废止整条 v3 旧设计；保留现行 v4 独立组合会话的业务含义 | 本轮废止；不能按字段名全局删除 | ADR-0003 `9b6b801`；v4 `83e93ad`、`0b8a266`；本轮用户决定，详见 §1 |
| v4 组合与结论 | AI chips/tool 自动写多字段卡、对话中判平衡 → 职责过载且用户缺乏结论主导权 | 一热爱＋多优势，一段用户填写的 `hypothesis`，确认后独立 AI 判平衡 | 已落地；业务语义与确认快照约束 | ADR-0015 `9e628e1`；`rumination_v4_service.py`，§2 |
| 前四阶段结论卡 | 多入口→单流→11轮门槛与直接出卡按钮→门槛撤销 | 自然出卡无最小轮数；手动按钮常驻于可用状态，点击先 judge，通过再生成 | 已落地；不属于 v4 chips/tool 清理范围 | #87 → `1a98a71` → `a513961`；0927 全景文档，§3 |
| 激活人与购买者 | 买码即被当作资源所有人容易串权限 | 订单购买者与激活使用者独立；赠送者仅经授权可看报告，对话不随报告共享 | 已落地；隐私与授权边界 | ADR-0010 `7792799`；#45；`48490f8`，§4 |
| 套餐交付／升级 | 购买时自动绑定并升级试用 → 妨碍转赠、语义混乱 | 季度1码、年度3码，全量未绑定；明确消耗一枚完整码升级现有试用 | 已落地；交付及追溯约束 | ADR-0014 `bc67930`；`simple_activation_manager.py`，§5 |
| 有效期／续期 | 首次使用起算；¥20/90天延期 | 新套餐码支付交付起算；旧空到期完整码保留首用兼容；免费一次7天、付费¥9.9/7天 | 已落地；兼容不能等同于新产品规则 | #57 → ADR-0018 `1ea1f73`/`2f7763c`；ADR-0016 `719ebd0`，§5 |
| 年度价格 | ¥99→¥128；后来 ADR 又写¥159 | 代码默认仍¥128；¥128有已实施依据，¥159未找到代码落地证据 | 代码事实与未落地决定分开；不能自动改价 | #67、`b123969`；ADR-0014，§6 |
| 会员与新订阅 | 会员被误当作购买激活码或通用资格 | 老 monthly/lifetime 预留明确保留且默认未开放；新月/年订阅另建语义，不重定义 lifetime | 有条件保留／新实现未开始 | ADR-0006/0007 `7792799`；ADR-0024 `48490f8`，§7 |
| 支付确认 | 官方回调唯一成功来源 → 回调未到导致已付款不交付 | 验签回调＋服务端主动查单＋定时对账；浏览器跳转不证明已付款 | 已落地；支付真实性与幂等约束 | ADR-0005 → #57；`0b8a266` 后支付实现，§8 |
| 退款 | 任一码使用即整单不可退 | 统一申请审批；按明细行分摊实付和未用权益判断全退／部分退 | 已落地；金额、渠道幂等和撤权约束 | `8074208`→`3992ec5`→`017e946`→`6234050`；#102，§8 |
| 优惠券 | 单槽锁定/核销字段只容一单 | `coupon_redemptions` 按行；多次券每用户一次；旧裸码永久精确匹配 | 已落地；兼容和账务守恒 | `fdc54a0`→`c2a423b`→`65fd892`→`a969b68`；#101，§8 |
| 报告审核 | ensure_report 即计时→进报告页计时；随机3–24h | v4终选提交即计时和预生成；报告页懒触发兜底；固定24h，旧 pending 不重算 | 已落地；事件时间、缓存与状态约束 | ADR-0009 → #83/`349c40d` → #91/`7a48de7`，§9 |
| 报告复核与生成 | 用户可反复重新生成 | 复核单＋staging新稿＋管理员确认发布；后台受权 force 保留 | 已落地；UI限制不等于删除运维能力 | #80、`tasks/report-review-plan.md`、`a5a96ad`，§9 |
| 报告引擎 | WeasyPrint与xunlu双引擎可切换且默认旧引擎 | 唯一xunlu静态渲染器；失败显式暴露；重新渲染不重新调用LLM | 已落地；母版、构建产物另有保留条件 | ADR-0019 `9d0a611` → ADR-0021 `6c9c766`，§10 |
| 存储演进 | SQLite＋JSON 双写，缺一致快照 | 混合存储仍为实现事实；JSON全入SQLite是暂缓计划；PG仅条件触发 | 未落地；不能先删JSON、锁或补偿 | ADR-0011 `7ab2bc9`；#59及关闭评论，§11 |
| 用户统计与筛选 | 各接口分别定义“付费”“报告”等 | 事件漏斗、筛选stage、实际访问权限是三种口径，不能互相替代 | 已落地；统计语义和授权分离 | ADR-0013 `bc67930`；ADR-0023 `af6479b`，§12 |
| 登录安全 | 无防爆破→5次锁15分钟；refresh并发误杀 | 阶梯锁定；UTC时间比较；10秒轮换宽限；统一刷新入口 | 已落地；进程内状态有单进程边界 | #81 → `b9bfd4f`；#85/`def325a`，§13 |
| 前端设计 | 多层玻璃卡与用户本地外观→多轮验收→性能修复 | guided布局、全局admin外观；指定聊天范围静态皮肤；功能状态不随设计稿删减 | 已落地／部分范围提案；历史“禁止改”有作用域 | 0919迁移决策、`15f30dc`；ADR-0022；#103，§14 |

## 1. v3 被废止的是什么，v4 必须保留的是什么

[ADR-0003](adr/0003-step3-combo-matrix.md)（`9b6b801`）把 v3 Step3 改为热爱×优势矩阵：`combo_id` 如 `"02"` 表示两个索引，消息仍在一个 `main_flow.json`，靠标签分组；Step3b 为跨组合公共讨论。相关 #18/#19/#23/#41 等旧问题仍有未关闭记录，不能因此要求恢复已被本轮用户废止的产品路径。

[0707实施总结](../wiki/历史开发记录/0707-tag1.6.0-实施总结.md)（`83e93ad`）是 v4 初期并行试验的快照，写有 URL/localStorage 试用开关、v3端点保留、迁移脚本“本次不实现”。[7-25实施口径](../wiki/历史开发记录/7-25-rumination-v4-实施口径.md)（`0b8a266`，后经 `9e628e1` 修订）已改变部分行为；基线前端正式入口仅走 v4。早期“v3默认不变”不是当前界面规则，更不是永久保留命令。

**同名字段不是同一概念。** 基线 [v4服务](../src/backend/app/services/rumination_v4_service.py) 的 `combo_sessions[].combo_id` 是 `combo_1` 一类独立会话标识，API 路径和 `selected_combo_ids` 都使用它；并非 v3 两位矩阵索引。现行 v4 一热爱＋多优势，最多10组，同热爱与严格相同优势集合判重；每组有独立 messages、用户卡、判定结果。按 `combo_id` 文本全仓删除会破坏 v4。删除审计应按模块、路由、协议与数据含义识别 v3。

本轮用户取消了 v3 代码与旧设计的保留要求。历史文件可以保留在 Git 追溯，不必以可执行兼容代码留存。该授权不等于已经验证服务器有无旧数据，也不等于授权在此次研究中擦除真实用户历史数据。

## 2. v4 提示词、卡片与平衡点

[#68](https://github.com/LYDONLUCIEN/BeingDoing/issues/68)及[关闭说明](https://github.com/LYDONLUCIEN/BeingDoing/issues/68#issuecomment-5103750298)（7月28日）纠正 v3 话术混入 v4：恢复咨询式引导、独立匹配讨论、无机械“四要素一票否决”；“终止讨论”是建议放弃的话术，不强制锁死用户输入。原生提示词文档被指定为内容源，但其工程附加协议随后再次改变。

[ADR-0015](adr/0015-user-driven-card-async-balance-judge.md)（`9e628e1`）明确取代7月版本的 chips、tool写卡、双信号和主对话判平衡。当前 `hypothesis` 是整个组合的一段用户字符串，旧按优势分项的字典与 motivation 等多字段不是新写入契约。主对话负责咨询；用户确认后独立后台AI根据组合、卡、对话判定。改卡或继续聊使原判定失效；分析期间仅当前组合输入和卡锁定；失败可重试，进程重启遗留任务转失败。未确认／跳过卡不参与完成检查；已确认卡须判定完成；不推荐只警告，不剥夺终选权。

当前 v4 代码仍含兼容读取旧 v4 多字段的归一化。这与 v3 是否保留是两个问题。旧文档中的 `uidesign/prompt/...` 指定来源在干净克隆中可能缺失，不能假装已读取；当前可核验主源是 [rumination_v4_prompt.py](../src/backend/app/domain/rumination_v4_prompt.py)、服务和 ADR。修改内容准则时应补齐原始来源或形成新的明确产品决定。

## 3. 前四阶段结论卡不是 v4 卡片

[#87](https://github.com/LYDONLUCIEN/BeingDoing/issues/87)完整记载了3月多路判定、4月单链路收敛、8月手动兜底的原因；其中11轮门槛、点击直接出卡均已过时：`1a98a71`（9月2日）撤销自然出卡的轮数压制，`a513961`（9月28日）落实9月27日“常驻按钮＋点击先判定”。因此不能把 #87 的初版要求抄进新开发规范。

现行证据为 [0927结论卡机制全景](../wiki/历史开发记录/0927/结论卡机制全景.md) 与 [simple_chat_routes.py](../src/backend/app/api/v1/simple_chat_routes.py) 的 `request_conclusion_card`：按钮在有用户消息、无待表态卡且线程未完成等条件下显示；judge通过才生成草案，未通过输出引导，失败明确报错。自然出卡和拒绝后retrigger是不同路径。前四阶段仍有 STATE_JSON 与 pending/confirmed/rejected 状态，不能随 v4 已淘汰的 tool/chips 协议一起删除。文档“pending判定器近乎死路径”只说明可达性疑点；其删除需要引用／路由核验，不能只看旧issue一句“死代码”。

## 4. 账户、购买、激活与报告授权

[ADR-0010](adr/0010-code-purchaser-activator-report-auth.md)（`7792799`）决定购买者 `purchaser_user_id` 与激活人 `owner_user_id` 分离，赠送者需获得 `report_authorized` 才可看报告，对话原文从不随此授权共享。`source_order_id` 是交付追溯，不直接授予报告或聊天读取权。

[#45](https://github.com/LYDONLUCIEN/BeingDoing/issues/45)记录 admin 调试污染真实激活码、手改JSON导致归属与report断链的原因：写入测试使用沙箱，读取用户资料不需要冒充owner；归属迁移须同步激活码和canonical report，留审计。该issue所称“原子迁移”不能单独证明跨JSON文件的数据库级事务，后续 ADR-0011 正是为双写失败问题提出改造。

`48490f8` 的权限修复是本轮新的实现证据。新开发文档应继续以真实 `role`／`is_super_admin_user` 和资源归属检查授权；`user_type=admin` 是运营标签，不能当管理员凭据。[ADR-0023](adr/0023-user-filter-registry.md)与[ADR-0024](adr/0024-shared-account-product-boundaries.md)都要求身份、交易、权益分开。

## 5. 套餐、消耗升级与有效期的替代链

[ADR-0008](adr/0008-packages-trial-vs-full-codes.md)（`7792799`）引入trial/full与套餐，旧单一SKU退场。[#58](https://github.com/LYDONLUCIEN/BeingDoing/issues/58)及[评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/58#issuecomment-5082487690)说明旧激活码缺字段时补full、保留未知字段、先备份；当时关闭的是脚本交付，不证明生产已执行。

[ADR-0014](adr/0014-unbound-delivery-consume-to-upgrade.md)（`bc67930`）取代自动升级／自动绑定：全量未绑定码可转赠；升级是“消耗一个完整码，把权益加到原试用码”，保留原码和探索链。`consumed_into` 与 `upgraded_from_code` 用于追溯，`consumed` 不是简单过期。只有显式 `intent=upgrade_trial` 的购买意图走自动消耗，不把所有购单都解释为升级。历史已绑定订单不倒改。

[#57](https://github.com/LYDONLUCIEN/BeingDoing/issues/57)的“完整码首次探索起算”后来被 [ADR-0018](adr/0018-package-validity-starts-at-purchase.md)（`1ea1f73`、`2f7763c`）替代为新码支付交付时起算；存量完整码 `expires_at=None` 继续首用起算，而 trial 的同一空值表示不限期。升级继承来源码剩余期限，不能从升级时重新赠送完整时长。

[#67](https://github.com/LYDONLUCIEN/BeingDoing/issues/67)的¥20/90天延期被 [ADR-0016](adr/0016-free-7day-renewal-and-9.9-paid-renewal.md)（`719ebd0`）替代：合资格完整码一次免费7天须owner主动领取；付费¥9.9/7天、不限次数、延期订单不可退。旧价用于历史订单解释，不是当前可售SKU；未登录服务器核实部署。

## 6. 年度价格：已实施的128与未找到落地的159

[#67](https://github.com/LYDONLUCIEN/BeingDoing/issues/67)与[完成评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/67#issuecomment-5103750851)明确7月28日从¥99改为¥128；提交 [`b123969`](https://github.com/LYDONLUCIEN/BeingDoing/commit/b123969)确实把 `ANNUAL_PRICE=9900` 改为12800。故当前默认¥128有明确产品和实施依据，不是来源不明的偶然值。

但更晚 [ADR-0014](adr/0014-unbound-delivery-consume-to-upgrade.md)（8月5日，`bc67930`）又写“12800→15900”。到核对基线 [settings.py](../src/backend/app/config/settings.py)仍12800，支付目录读取此配置；对该配置做Git变更检索未找到15900落地提交。准确分类是：**¥128已实施；后续¥159有决策文字，但未查到代码实施，也未查到明确撤销该决定的证据。** 不应把7月 #67 说成推翻8月ADR，更不应在清理中自动把当前价格改159。运行环境可覆盖默认值，本研究未读取线上配置。新文档应记录当前代码默认，并将历史159单独登记为未落地决策差异。

## 7. 明确保留的会员预留与新产品边界

[ADR-0006](adr/0006-membership-vs-activation-code-two-product-lines.md)／[0007](adr/0007-membership-built-but-not-launched.md)（`7792799`）将会员与消耗型激活码分成产品线；会员不等于免费探索码，`vip_level` 是旧探索模型档位。自动续扣因签约条件未齐没有上线，会员表／用户字段／接口预留且 `MEMBERSHIP_ENABLED=False`。这是明确保留理由，不可仅因当前UI无入口删除。

[ADR-0024](adr/0024-shared-account-product-boundaries.md)（`48490f8`）确定新产品共享 `users.id`，交易、订阅周期、产品权益、探索和报告分别建模；老 `monthly/lifetime` 不能原地改成新产品 `monthly/annual`。新产品不必发行激活码，也不能以运营标签、付款记录或vip_level推导通用权限。该ADR是边界决定，不是购物车、自动扣款和新订阅表已经实施的证明。团队分析的隐藏 `page.impl.tsx` 同样有基线明确保留要求；本轮取消v3保留不自动取消其他保留项。

## 8. 支付、退款与优惠券

[ADR-0005](adr/0005-payment-dual-channel-official-gateway.md)（`7792799`）拒绝个人收款码＋人工确认，选择官方渠道。其“回调唯一成功来源”被 [#57](https://github.com/LYDONLUCIEN/BeingDoing/issues/57)的真实故障处理扩展为：验签回调、服务端主动查单、定时对账，仍不能信任浏览器支付回跳。支付宝从precreate改page.pay有开通条件原因；双渠道设计不能推断两个渠道在每个部署均已开通。

早期“任一码使用就不能整单退款”被 [10-05退款设计](../wiki/历史开发记录/10-05/订单系统退款设计.md)、[#102](https://github.com/LYDONLUCIEN/BeingDoing/issues/102)与四阶段实现（`8074208`、`3992ec5`、`017e946`、`6234050`）替代。当前以 `payment_order_lines` 分摊原价、优惠、实付，以 `payment_refunds` 记录申请与批准金额；按可退款明细行和商品限制执行，审批时重验，批准额不能超过可退实付。`partially_refunded/refunded` 是累计退款金额口径，不是“所有码都作废”口径。旧直接退款接口返回废弃，统一走申请单。渠道退款幂等标识重试必须复用，不能为美化状态机删掉失败重试分支。

[10-06多次券定稿](../wiki/历史开发记录/10-06/优惠券多次核销与码格式区分-设计定稿.md)与[#101](https://github.com/LYDONLUCIEN/BeingDoing/issues/101)由 `fdc54a0`、`c2a423b`、`65fd892`、`a969b68` 落地：一次券单槽历史字段保留兼容，多次券用核销行和条件UPDATE占用名额；同用户同券一次，n>1不能绑owner；部分退款不按比例退券，满足规则的全退返还核销名额。新码格式区分券与激活码，**旧裸码精确匹配永久兼容**是明确决定；不要把“旧格式”当作应删除数据。上述issue仍列生产迁移待办，本研究不能替其确认迁移023/024已在线上执行。文档“原子联动”也不是对SQL＋JSON跨存储原子性的验证结论。

## 9. 报告审核、复核与内容权威

[ADR-0009](adr/0009-report-review-auto-approve.md)（始于 `7792799`，后修订）先纠正“刚创建report就开始审核”的提前计时，改为完成五阶段后访问报告页触发；[0823文档](../wiki/历史开发记录/0823-提交即审核与报告页异常态.md)／[#83](https://github.com/LYDONLUCIEN/BeingDoing/issues/83)（`349c40d`）再前移到v4终选提交，解决用户不进报告页就永远不生成。报告页懒触发仅是旧 `not_started` 与异常兜底，不能恢复为唯一入口。

[#91](https://github.com/LYDONLUCIEN/BeingDoing/issues/91)及[完成评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/91#issuecomment-5558759399)（`7a48de7`）把随机3–24h改固定24h，旧pending按原deadline；扫描存在间隔，所以不是秒级承诺。生成看门狗在间隔和次数限制下重试，不能保证外部模型永不失败。旧文案将自动批复描述为人工审核，这是历史产品选择；应单独列为用户沟通口径问题，不能提升为必须永久隐瞒自动化的工程约束。

[报告复核计划](../tasks/report-review-plan.md)／[#80](https://github.com/LYDONLUCIEN/BeingDoing/issues/80)（`a5a96ad`）取代用户任意重新生成：内容问题走复核单，下载问题走Feedback；staging新稿在管理员发布前不替换旧稿，发布备份旧稿。**后端受权force能力明确保留供运维**，不能从“管理员也不能随意生成”的UI标题推导删去后端能力；更不能开放给普通用户。生成失败的重试与已完成报告的内容重生成也不是一回事。

[#89](https://github.com/LYDONLUCIEN/BeingDoing/issues/89)要求报告方向严格使用用户终选结论与平衡点结果，不能由模型从完整对话自行改选方向；仅影响新生成／复核新稿，不回写旧Markdown。当前主源是 [report_system.yaml](../src/backend/app/domain/prompts/templates/report_system.yaml)与 [report_pdf_service.py](../src/backend/app/services/report_pdf_service.py)。

## 10. PDF引擎、母版与后处理

[ADR-0017](adr/0017-report-post-processing-pipeline.md)（`aa02922`、`019b67f`）把报告生成后处理拆为确定性规范化和局部LLM压缩，失败保原文；其旧版标题／分页阈值具有渲染器时代背景，不能直接据数值复制新规范。已有Markdown重渲染和LLM重新生成必须区分。

[ADR-0019](adr/0019-xunlu-pdf-renderer.md)（`9d0a611`）从设计工程抽出 `src/report-renderer`：React服务端静态HTML＋Node/Chrome子进程，无常驻前端服务或RSC产品链路。[ADR-0021](adr/0021-single-xunlu-report-renderer.md)（`6c9c766`）因生产仍落在旧默认引擎而废止双引擎／运行时切换／WeasyPrint报告兜底，当前 `ReportPDFService.markdown_to_pdf` 直接调用xunlu。

保留条件：`report/xunlu` 是只读设计母版，`src/report-renderer/dist` 是生产运行构建产物，应随源码构建更新；不能凭“生成目录”通用规则删除。模板中的旧品牌名也不等于产品仍使用旧品牌。ADR-0021曾因会话导出要求保留WeasyPrint，但 `5b461e6` 时该导出调用已不在现行实现中，requirements仍因明确历史保留文字留下。**“历史保留理由已失效但依赖仍保留”需重新决定，不应伪称现在仍有调用；也不能重新引入双报告引擎。**

## 11. 存储、归档与迁移并未被“关闭issue”完成

[历史存储说明](历史文档/DATA_STORAGE_SIMPLE.md)（`bbe8b1c`）解释report／阶段／thread目录及本地缓存角色；[ADR-0011](adr/0011-storage-evolution-sqlite-then-postgres.md)（`7ab2bc9`）承认JSON是早期便利选择，提出先全入SQLite、条件满足再PG。[#59](https://github.com/LYDONLUCIEN/BeingDoing/issues/59)明确“当前不执行”，[关闭评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/59#issuecomment-5082560687)明确待验收后重开。tag只是前置条件之一，v1.8.0存在不证明迁移已完成。

基线 [SimpleActivationManager](../src/backend/app/utils/simple_activation_manager.py)、[ReportRegistry](../src/backend/app/utils/report_registry.py)和v4服务仍读写JSON；账户、交易等在SQL。故“迁移后删锁和补偿”“JSON不再是主源”都属于未发生阶段的后果，不能先行执行。PG触发条件是多worker、频繁锁库或扩容场景；不存在“本次整理必须换数据库”的决定。ADR里的锁能力描述是当时风险判断，不替代对具体锁实现／部署拓扑的技术验证。

[#17](https://github.com/LYDONLUCIEN/BeingDoing/issues/17)显示thread删除采用软归档防幽灵恢复，其[后续评论](https://github.com/LYDONLUCIEN/BeingDoing/issues/17#issuecomment-4525687328)又修正了最初“前端完全按remaining_thread_ids过滤”的策略，改按目标ID和当前state处理竞态。不能恢复初版做法。[#53](https://github.com/LYDONLUCIEN/BeingDoing/issues/53)的孤儿／缺失线程仍是待评估记录，不是应自动批量删除的授权。

[0821迁移手册](../wiki/历史开发记录/0821-迁移计划-v1.5.1-to-v1.6.0.md)与[0917升级指引](../wiki/历史开发记录/0917-生产升级指引-v1.6.0-to-v1.6.1.md)记录的是特定旧版迁移和回滚。保留能解释数据的迁移链、备份/归档约定；历史主机、默认引擎、数据库revision和命令不应直接抄为今天一键部署流程。仅凭 `.duplicate/`、`data_backup/` 或回收站名称不能认定内容可丢弃。

## 12. 统计字段不能替代权益或权限

[ADR-0013](adr/0013-analytics-funnel-event-time-sqlite.md)（`bc67930`）是事件时间漏斗，各阶段独立计数，不是同一注册cohort；历史“纯利润”实为收入口径，没有完整成本，不能传播成财务利润。分析事件与业务同SQLite，不引入第二分析库；PV等无源历史不回填。

[ADR-0023](adr/0023-user-filter-registry.md)（`af6479b`）给筛选字段明确但有限的含义：`paid_status`按特定订单状态，不能推断当前权益或所有历史付费；`code_kind`取未consumed码最高档且包括过期码；`stage=report_unlocked`按任一report五阶段锁定，不等于审核approved，更不是下载权限已经通过。漏斗报告事件用审核时间，是另一指标。字段内OR、字段间AND；旧扁平导出参数有部署兼容层，约定下一大版本移除而非现在随手删。`MAX_EXPORT_USERS=50`、多产品共用注册表是已决定边界；预聚合/筛选DSL/独立pip包是未启动方案。

## 13. 认证与安全历史中的两次替代

[`a2791e5`](https://github.com/LYDONLUCIEN/BeingDoing/commit/a2791e5)引入双token刷新和admin能力；[#85](https://github.com/LYDONLUCIEN/BeingDoing/issues/85)解释SQLite时间naive/aware比较和并发刷新撤整族的问题，`def325a`修复UTC比较、统一前端single-flight与10秒轮换宽限。宽限窗外仍检测重用，不能为避免掉线把重放防护整段删去。

[#81](https://github.com/LYDONLUCIEN/BeingDoing/issues/81)的“5次失败锁15分钟”已被 `b9bfd4f`（9月19日）取代。基线 [auth_service.py](../src/backend/app/services/auth_service.py)按标识计数、前5次不锁，第6/7/8/9次分别锁1/2/5/10分钟，之后10分钟；首错起满一小时重置，锁定重试不续期。不存在账号也计数并走假哈希，普通错误统一。进程内计数重启丢失、多worker不共享是当前实现边界，不是永久免改的安全保证；旧issue“明确不做IP限制”等只是该次范围。

[#32](https://github.com/LYDONLUCIEN/BeingDoing/issues/32)对应 `8f8dbce` 修正邮箱验证JWT用途被access覆盖；[#97](https://github.com/LYDONLUCIEN/BeingDoing/issues/97)与[1004完成记录](../wiki/历史开发记录/claude-completed-1004-邮箱验证状态自动同步.md)（`2d2b290`）解决旧标签页store不同步，而非邮箱点号或后端验证延迟。不能因此修改邮箱归一化来合并不同账号。调查中issue仍写待提交，但Git已有提交，这是issue状态落后于仓库的实例。

[早期admin计划](../tasks/admin-development-command-center.md)（`e5295b7`、`37de823`）记录独立子域＋super_admin＋step-up目标，混合已做和待办；需以当前路由依赖证明检查覆盖，不能拿文档标题证明所有admin操作都已二次验证。

## 14. 前端设计：限定阶段的保护线不能永久化

[ADR-0004](adr/0004-rumination-v4-shell-layout.md)（`37a9904`）的v3玻璃视觉＋单shell是当时迁移策略。[0919迁移决策记录](../wiki/历史开发记录/0919/迁移决策记录.md)（`356809a`→`15f30dc`）之后明确允许重画rumination并覆盖旧保护线，要求保留业务状态机、真实后端能力与设计稿未覆盖功能；不能用“功能并集”要求永久保留用户后来明确淘汰的v3。

同一文件含多轮彼此覆盖的决定：保留副标题→删除；用户localStorage外观弹层→admin全局外观；新建组合紫虚线→黑色→浅渐变→最终黑色；三栏guided成为默认；整页和聊天外层玻璃卡删除。读取时必须走到末次验收，不能选第一张“已拍板表”。“PurchaseModal完全不动”是此次换肤的范围约束，后续支付需求仍可改它。

[ADR-0022](adr/0022-static-performance-skin.md)（`f85b5ee`、`bd8d66f`）与[#103](https://github.com/LYDONLUCIEN/BeingDoing/issues/103)又替代聊天前四阶段与v4的动态装饰/blur：冻结装饰动画、实色表面，保留功能性思考/加载/庆祝反馈；性能方案初版导致三段色带，被用户三轮否决，最终透明header／融底输入／静态渐隐条形成连续画布。该约束不是全站禁用所有动画或所有mask；dashboard/home第二阶段在ADR中仍属后续范围。历史截图测试和60fps声明未在本研究复测。

[ADR-0020](adr/0020-old-browser-kernel-compat-floor.md)（`7a48de7`）保留特性检测、vh/dvh与颜色静态回退；旧内核提示不是承诺IE完整可用。品牌 [ADR-0012](adr/0012-rebrand-xunlu-to-openlife.md)要求用户新文案使用寻路·OpenLife，但刻意不改内部服务名、缓存key和设计母版。内部旧称可追溯，不应为了词面统一造成兼容破坏。

## 整理时可直接采用的判定

| 候选内容 | 证据支持的处理 | 不应据此推导 |
|---|---|---|
| v3 Step3矩阵/3b/旧提示词/接口及其专属测试和使用文档 | 本轮用户明确淘汰；以Git保存历史，清理现行入口与引用 | 删除v4同名combo_id；删除真实历史数据 |
| v4旧chips/tool/双信号/多字段出卡文档 | ADR-0015明确替代；从现行指南移除，必要历史来源留Git链接 | 删除前四阶段STATE_JSON或现行结论判定 |
| 11轮门槛、5次锁15分钟、随机审核3–24h | 均有更晚提交替代，应纠正文档 | 将旧issue closed视为最新规范 |
| 双PDF引擎切换、旧WeasyPrint报告代码 | ADR-0021明确淘汰 | 删除设计母版、dist或未经重新判定的保留依赖 |
| FLOW_REFACTOR_PLAN等旧方案未勾选任务 | 降为历史提案，不进入当前开发待办 | 自动恢复LangGraph/full老架构或执行未确认迁移 |
| 旧裸码、expires_at空值完整码、旧订单金额 | 保留明确兼容解释与读取规则 | 把旧产品值批量转换成新语义 |
| 会员预留、团队分析实现、迁移/归档约定 | 存在明确保留依据；单列状态与开放条件 | “无UI入口就是死代码” |
| JSON→SQLite、PG、新订阅/购物车 | 保留为带条件的未实施演进议题 | 在cleanup中顺带迁数据或开自动扣费 |
| ¥159与当前默认¥128 | 记录已实施价格及未落地差异 | 无证据改价或宣称线上售错价 |

后续正式开发文档应只呈现现行契约；历史原因、替代链和未落地差异由本文件及原始Git/issue承接。若本轮实现改变上述基线行为，应补新的提交和验收证据，而非悄悄改写历史为“从来如此”。
