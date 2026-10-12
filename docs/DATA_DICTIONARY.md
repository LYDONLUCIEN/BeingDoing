# 字段与状态字典

核对 v1.8.0 + clean 安全边界。这里描述现存数据，不执行改名/迁移。金额均为整数分；持久化时间通常为 UTC，SQLite DateTime 读出可能无 tzinfo，按 UTC 解释后比较。统计日桶使用 Asia/Shanghai。NULL、空串、字段缺失按各列语义处理，不统一视作未使用。

## 身份与访问

| 字段 / 来源 | 含义 | 空值、更新者和约束 |
| --- | --- | --- |
| users.id；JWT sub；API current_user.user_id | 跨产品账户主键 | UUID 字符串；新产品继续引用这个身份，不按邮箱另建账户 |
| users.email / phone | 联系与登录标识 | 可空，不能作为跨产品永久主键；现注册需邮箱，存量手机号存在 |
| users.username / survey.nickname | 展示昵称 | 昵称可变；问卷缺省回填，不能参与授权 |
| users.user_type | real/beta/test/admin 运营分组 | 默认 real；admin 标签不授权。真正权限由 SUPER_ADMIN_* 与 is_super_admin_user 决定 |
| users.email_verified / is_active / deleted_at | 邮箱验证、启用、注销状态 | 不同维度；恢复账户 token 受限，不可当普通登录态 |
| membership_plan / membership_expires_at | 老会员缓存 | none/monthly/lifetime，未上线；lifetime 绝不等于新 annual |
| refresh_tokens.user_id / family_id / is_revoked | 刷新令牌所属账户、轮换族、撤销标志 | 只存令牌哈希；重置密码撤销该账户所有刷新令牌；既有 access token 仍受原有效期限制 |

来源：[User](../src/backend/app/models/user.py)、[RefreshToken](../src/backend/app/models/refresh_token.py)、[授权函数](../src/backend/app/utils/super_admin.py)。邮箱、手机号、令牌、问卷/对话、报告均是敏感数据；调试日志与导出也继承敏感性。

## 激活码、探索、报告：不要混用 ID

| 字段 | 当前含义与权威来源 | 容易混淆之处 |
| --- | --- | --- |
| code / activation_code | 激活资格标识，activations.json | 新格式与存量裸码共存；知道码不等于可看任何报告 |
| purchaser_user_id / source_order_id | 购买者与交付来源订单 | purchaser 可以不是实际使用者 |
| owner_user_id / owner_email / claimed_at | 激活人，owner_email 为历史兼容 | 未绑定完整码 owner 为空；不可因此放行私有内容 |
| code_type / vip_level | trial/full 产品资格；1/2 历史模型档位 | vip_level 不是账户会员、不是固定供应商；模型由场景/运行配置解析 |
| package_type | quarterly/annual/空，码来源套餐 | 不是订阅周期；延期现已统一价格 |
| expires_at | ISO 时间串/空；码的有效期 | trial 空=不限期；存量 full 空=延迟起算；不能将 full 空直接判为永久 |
| status / consumed_into / upgraded_from_code | active 等码状态；消耗升级双向审计 | consumed 是已转移资格，不是简单过期；不得再退款/认领 |
| activation_session_id | simple 探索根会话标识 | 不是数据库 Session.id 的通用替代 |
| ActivationRecord.session_id | 历史会话引用，仍兼容 | 不同链路使用有差异，不能新建接口只叫 session_id 而不注明所属模型 |
| Session.id / user_id | 旧 SQLite 对话会话与所属账户 | 旧 /chat、/answers、/export 的权限按此归属判定 |
| report_id | 报告记录标识 | activations 上仅快速索引；权威为 reports/{report_id}/record.json |
| thread_id；record.steps[*].session_ids | 阶段内独立对话线程 | record 的 session_id 字样在此表示线程，不是账户/激活码 |
| selected_session_id / locked | 选定阶段线程与阶段锁定 | rumination 以 locked 作为完成信号，前四阶段需有效选择；复用 _report_portal_unlocked |
| report_authorized | 激活人对对应购买者的报告授权 | 不授权对话；新产品查询仍必须验证归属/授权与审核 |
| review_status / review_deadline | not_started/pending_review/approved 等审核状态与期限 | 五阶段完成不等于审核通过；审核通过也不代替资源授权 |

来源：[ActivationRecord](../src/backend/app/utils/simple_activation_manager.py)、[ReportRegistry](../src/backend/app/utils/report_registry.py)、[旧 Session](../src/backend/app/models/session.py)。

## 对话、沉淀与统计

| 字段 | 定义与边界 |
| --- | --- |
| phase / current_step / dimension | values/strengths/interests/purpose/rumination 是当前主阶段；旧 Agent dimension 名称不同，聚合需显式映射 |
| passions / strengths | 沉淀输入的热爱与优势；interests 是阶段名，passions 是提炼结果 |
| v3 combo_id / v4 combo session | v3 是两索引格子；v4 独立组合含一热爱和多优势，不按索引自动转换 |
| hypothesis | 用户填写字符串，不是按优势分组的 dict |
| balance_found / balance_fail_reason | 后台对确认快照的判断及理由；新消息/修改假设使判断失效；不是强制准入 |
| AnalyticsLike.user_id / message_id | 点赞者与消息 ID；新写入必须有已认证用户，读写按用户过滤 |
| AnalyticsLike.session_id | 历史混用：前四阶段传 activation_session_id，v4 传 activation_code；当前兼容并校验归属，不据此拼路径 |
| content_snapshot / content_preview | 客户端提供的私有内容快照/预览，不能当可信服务端原文或 HTML；trace 不再按客户端路径扫描文件 |
| visitor_id / page_view / auth_active | 匿名访客标识/PV/登录活跃事件；PV 可公开上报，auth_active 仅服务端写；不是登录用户数同一口径 |
| paid_status | ADR-0023 筛选口径：存在 paid/granted 订单为 paid；partially_refunded 不计，明确不是终身付费用户标签 |
| code_kind / stage | 非 consumed 码最高档 full>trial>none（过期仍计）；stage 取多记录最前进度，与审核结果不同 |

历史 user_id 为空的点赞不推断归属、不公开给任意人；若要迁回账户，需用可信数据验证后单独迁移。

## 交易、退款与优惠券

模型都在 [payment.py](../src/backend/app/models/payment.py)。

| 字段 | 定义、单位、约束 |
| --- | --- |
| PaymentOrder.id / order_no / user_id | 内部订单 ID / 商户订单号 / 购买者；不是激活人 |
| product_type / quantity / meta | 现有单商品订单的产品分支及交付载荷；quantity 不是现成的购物车支持 |
| amount_original / amount_discount / amount_paid / amount_refunded | 原价/优惠合计/实付/累计成功退款，整数分；退款不得超过实付 |
| status | pending→paid→granted；另有 closed/cancelled/refunding/partially_refunded/refunded；支付成功与权益交付分离 |
| delivered_code / meta.codes / gift_codes | 历史交付码字段与多码集合，展示取并集去重；不能仅看 delivered_code 就遗漏年度其余码 |
| qr_code / pay_url / qr_text | 数据库 qr_code 兼容名实际存跳转 URL/凭证；qr_text 是用于自绘二维码的内容，提取失败可空并回退 |
| PaymentOrderLine.item_type / item_ref | code/consultation_service/renewal_service；引用码、预约或目标码 |
| price_original_alloc / coupon_alloc / amount_paid_alloc | 行分摊原价/优惠总额/实付，尾差归最后一行；coupon_alloc 名称虽然写 coupon，实际含所有优惠 |
| PaymentOrderLine.status | 持久核销记录；可退性还需实时查认领/消耗/预约，不能只看 available |
| PaymentRefund.requested_amount / approved_amount / refund_no | 申请额/批准执行额/渠道幂等号；同单一个待审批申请，成功才累计退款 |
| Coupon.max_uses / used_count / locked_count | 总次数（1..10000）/已核销/锁定中；容量守卫在 DB 原子更新 |
| owner_user_id / expires_at / suspended_at / voided_at | 单次券归属/期限/停用/作废；多次券不绑人；过期、停用、作废不是同一状态 |
| CouponRedemption.order_id / user_id / status | 一订单一次券记录；locked/used/released/refunded；新发生记录落表，旧单槽信息兼容保留 |

## 已确认冲突与待决定事项

1. 年度套餐历史定价决定 ¥159，而 settings 默认 ANNUAL_PRICE=12800。未读取线上覆盖值，不能认定线上售错价。本次保留价格，发布前由产品核对实际配置并决定统一值。
2. 老 AnalyticsLike.session_id、ActivationRecord.session_id 与 report thread 的同名不同义尚未迁移。新接口分别命名为 account_id/activation_code/exploration_id/thread_id/report_id，并声明映射；这些是命名建议，不是已存在的新列。
3. paid_status 排除部分退款是已接受筛选定义。若新产品要「历史有支付」或「当前有效订阅」，新增维度，不能悄改旧报表。
4. membership_monthly/lifetime 是保留能力，不代表新月/年订阅已经可售。按 [跨产品方案](PRODUCT_EVOLUTION.md) 设计后再迁移。
