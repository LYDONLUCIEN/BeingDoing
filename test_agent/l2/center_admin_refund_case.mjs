/**
 * Admin 退款前端改造验收（受控接口；不访问真实业务服务）。
 *
 * 覆盖点：
 * - 订单管理：pending / paid / granted / partially_refunded 均显示退款入口；
 *   code_refundable=false（已用码）不再禁用，只提示由审批确认；
 *   pending 提示需渠道确认已支付后才可批准；partially_refunded 提示可退剩余。
 * - 退款审批·代录：按订单号读取订单/退款项（adminFetchRefundOptions）；
 *   partial 按行选择（已被使用的行也允许勾选），未选行不可提交；
 *   提交携带 line_ids 与协商金额。
 * - 审批弹窗：含 code 行的退款单默认勾选「退款后作废已选激活码」；
 *   取消勾选后 approve 提交 revoke_codes=false；保持勾选提交 revoke_codes=true；
 *   非法金额 / 缺调整理由被前端拦截（按钮禁用 + 明确错误提示）。
 */

/** admin 登录夹具（与 center_admin_case 同口径：localStorage 写入超管会话） */
const ADMIN_USER = {
  user_id: 'center-refund-test',
  username: '退款测试管理员',
  is_super_admin: true,
  email_verified: true,
};

/** 订单列表夹具：覆盖 pending / paid / granted(已用码) / partially_refunded */
function buildOrders() {
  const base = {
    quantity: 1,
    amount_discount: 0,
    channel: 'alipay',
    created_at: '2026-10-18T10:00:00Z',
    user_email: 'buyer@example.com',
  };
  return [
    { ...base, id: 'o-pending', order_no: 'BD-TEST-PENDING', product_type: 'quarterly_package', amount_original: 30000, amount_paid: 30000, status: 'pending' },
    { ...base, id: 'o-paid', order_no: 'BD-TEST-PAID', product_type: 'quarterly_package', amount_original: 30000, amount_paid: 30000, status: 'paid' },
    { ...base, id: 'o-used', order_no: 'BD-TEST-USED', product_type: 'quarterly_package', amount_original: 30000, amount_paid: 30000, status: 'granted', delivered_code: 'CODE-USED-1', code_refundable: false },
    { ...base, id: 'o-partial', order_no: 'BD-TEST-PARTIAL', product_type: 'quarterly_package', amount_original: 30000, amount_paid: 30000, amount_refunded: 10000, status: 'partially_refunded' },
  ];
}

/** 退款能力视图夹具（partially_refunded 订单：行级分摊，含可用/已用/已退三态行） */
function buildRefundOptions() {
  return {
    order: {
      id: 'o-partial',
      order_no: 'BD-TEST-PARTIAL',
      product_type: 'quarterly_package',
      amount_paid: 30000,
      amount_refunded: 10000,
      status: 'partially_refunded',
    },
    full_allowed: true,
    partial_allowed: true,
    partial_by_lines: true,
    remaining_refundable: 20000,
    lines: [
      { id: 'line-1', line_no: 1, item_type: 'code', item_ref: 'CODE-P1', amount_paid_alloc: 10000, effective_status: 'available' },
      { id: 'line-2', line_no: 2, item_type: 'code', item_ref: 'CODE-P2', amount_paid_alloc: 10000, effective_status: 'used' },
      { id: 'line-3', line_no: 3, item_type: 'code', item_ref: 'CODE-P3', amount_paid_alloc: 10000, effective_status: 'refunded' },
    ],
    pending_request: null,
    history: [],
  };
}

/** 待审批退款单夹具：r1 部分退（含 code 行快照）；r2 全额退（验证默认勾选提交 revoke_codes=true） */
function buildRefunds() {
  return [
    {
      id: 'r1',
      refund_no: 'RF-TEST-1',
      order_id: 'o-used',
      order_no: 'BD-TEST-USED',
      user_id: 'u-buyer',
      user_email: 'buyer@example.com',
      originated: 'user',
      refund_type: 'partial',
      requested_amount: 15000,
      reason_user: '多买了一张想退',
      status: 'pending_review',
      line_snapshot: [
        { line_id: 'line-a', line_no: 1, item_type: 'code', item_ref: 'CODE-A', amount_paid_alloc: 15000 },
      ],
      created_at: '2026-10-19T09:00:00Z',
    },
    {
      id: 'r2',
      refund_no: 'RF-TEST-2',
      order_id: 'o-paid',
      order_no: 'BD-TEST-PAID',
      user_id: 'u-buyer',
      user_email: 'buyer@example.com',
      originated: 'user',
      refund_type: 'full',
      requested_amount: 30000,
      reason_user: '不想用了',
      status: 'pending_review',
      line_snapshot: [
        { line_id: 'line-c', line_no: 1, item_type: 'code', item_ref: 'CODE-C', amount_paid_alloc: 30000 },
      ],
      created_at: '2026-10-19T10:00:00Z',
    },
  ];
}

function buildRefundDetails() {
  const [r1, r2] = buildRefunds();
  return {
    r1: {
      ...r1,
      order: {
        id: 'o-used',
        order_no: 'BD-TEST-USED',
        product_type: 'quarterly_package',
        amount_paid: 30000,
        amount_refunded: 0,
        status: 'granted',
        coupon_id: null,
      },
      order_lines: [
        { id: 'line-a', line_no: 1, item_type: 'code', item_ref: 'CODE-A', amount_paid_alloc: 15000, effective_status: 'available', db_status: 'active' },
        { id: 'line-b', line_no: 2, item_type: 'code', item_ref: 'CODE-B', amount_paid_alloc: 15000, effective_status: 'used', db_status: 'active' },
      ],
    },
    r2: {
      ...r2,
      order: {
        id: 'o-paid',
        order_no: 'BD-TEST-PAID',
        product_type: 'quarterly_package',
        amount_paid: 30000,
        amount_refunded: 0,
        status: 'paid',
        coupon_id: null,
      },
      order_lines: [
        { id: 'line-c', line_no: 1, item_type: 'code', item_ref: 'CODE-C', amount_paid_alloc: 30000, effective_status: 'available', db_status: 'active' },
      ],
    },
  };
}

export async function prepareAdminRefund(context) {
  await context.addInitScript(
    user => localStorage.setItem('auth-storage', JSON.stringify({ state: { user, token: 'fixture-token', isAuthenticated: true }, version: 0 })),
    ADMIN_USER,
  );
  const orders = buildOrders();
  const refunds = buildRefunds();
  const refundOptions = buildRefundOptions();
  const refundDetails = buildRefundDetails();
  const state = {
    /** refund-options 被读取时使用的订单引用（验收支持订单号） */
    optionsRefs: [],
    /** 代录提交载荷 */
    createPayloads: [],
    /** 审批提交载荷 */
    approvePayloads: [],
  };

  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname;
    const method = route.request().method();
    let data = {};
    if (endpoint.endsWith('/auth/me')) data = ADMIN_USER;
    else if (/\/admin\/payment\/orders\/[^/]+\/refund-options$/.test(endpoint)) {
      // 代录弹窗「读取订单/退款项」：记录使用的引用（订单 ID 或订单号）
      state.optionsRefs.push(decodeURIComponent(endpoint.split('/').at(-2)));
      data = refundOptions;
    } else if (/\/admin\/payment\/orders\/[^/]+$/.test(endpoint)) {
      data = { order: orders.find(o => o.id === endpoint.split('/').at(-1)) ?? orders[0] };
    } else if (endpoint.endsWith('/admin/payment/orders')) {
      data = { items: orders, total: orders.length, page: 1, page_size: 20 };
    } else if (/\/admin\/payment\/refunds\/([^/]+)\/approve$/.test(endpoint) && method === 'POST') {
      const body = route.request().postDataJSON();
      const id = endpoint.match(/\/admin\/payment\/refunds\/([^/]+)\/approve$/)[1];
      state.approvePayloads.push({ id, ...body });
      data = { refund: { ...refundDetails[id], status: 'succeeded', approved_amount: body.approved_amount, revoke_codes: body.revoke_codes } };
    } else if (/\/admin\/payment\/refunds\/[^/]+$/.test(endpoint)) {
      data = refundDetails[endpoint.split('/').at(-1)] ?? {};
    } else if (endpoint.endsWith('/admin/payment/refunds') && method === 'POST') {
      const body = route.request().postDataJSON();
      state.createPayloads.push(body);
      data = { refund: { ...refunds[0], id: `r-created-${state.createPayloads.length}`, refund_no: `RF-CREATED-${state.createPayloads.length}`, originated: 'admin', status: 'pending_review', refund_type: body.refund_type, requested_amount: body.amount ?? 0 } };
    } else if (endpoint.endsWith('/admin/payment/refunds')) {
      data = { items: refunds, total: refunds.length, page: 1, page_size: 20 };
    }
    await route.fulfill({ json: { code: 200, message: 'ok', data } });
  });
  return state;
}

export async function testAdminRefund(page, base, state, check) {
  await page.goto(`${base}/admin/payment`, { waitUntil: 'networkidle' });

  // ── 订单管理：退款入口状态扩展 + 已用码不禁用 ──
  for (const orderNo of ['BD-TEST-PENDING', 'BD-TEST-PAID', 'BD-TEST-PARTIAL']) {
    const button = page.locator('tr', { hasText: orderNo }).getByRole('button', { name: '退款', exact: true });
    await button.waitFor();
    check(await button.isEnabled(), `${orderNo} 应显示可点击的退款入口`);
  }
  const usedButton = page.locator('tr', { hasText: 'BD-TEST-USED' }).getByRole('button', { name: '退款', exact: true });
  await usedButton.waitFor();
  check(await usedButton.isEnabled(), '已用码（code_refundable=false）不应禁用退款入口');

  // 已用码弹窗：提示由审批确认，代录按钮可用
  await usedButton.click();
  await page.getByText('是否退款及作废旧码由「退款审批」环节确认', { exact: false }).waitFor();
  check(await page.getByRole('button', { name: '代录申请' }).isEnabled(), '已用码订单的代录提交不应被禁用');
  await page.getByRole('button', { name: '取消', exact: true }).click();

  // pending 弹窗：需渠道确认已支付后才可批准
  await page.locator('tr', { hasText: 'BD-TEST-PENDING' }).getByRole('button', { name: '退款', exact: true }).click();
  check(await page.getByText('仅当渠道（支付宝/微信）确认已支付后才可批准退款', { exact: false }).isVisible(), 'pending 文案说明渠道确认前置');
  await page.getByRole('button', { name: '取消', exact: true }).click();

  // partially_refunded 弹窗：可继续退剩余
  await page.locator('tr', { hasText: 'BD-TEST-PARTIAL' }).getByRole('button', { name: '退款', exact: true }).click();
  await page.getByText('本次代录将继续退剩余部分', { exact: false }).waitFor();
  check(await page.getByText('已退 ¥100.00', { exact: false }).isVisible(), 'partially_refunded 展示已退与剩余金额');
  await page.getByRole('button', { name: '取消', exact: true }).click();

  // ── 退款审批·代录：按订单号读取行，partial 必须选行（已被使用的行也允许勾选）──
  await page.getByRole('button', { name: '退款审批' }).click();
  await page.getByRole('button', { name: /代录退款申请/ }).click();
  const orderInput = page.getByPlaceholder('订单 ID 或订单号');
  await orderInput.waitFor();
  const submitCreate = page.getByRole('button', { name: /代录并待审批/ });
  check(await submitCreate.isDisabled(), '未读取订单退款项时不可提交');
  await orderInput.fill('BD-TEST-PARTIAL');
  await page.getByRole('button', { name: '读取订单/退款项' }).click();
  await page.getByText('剩余可退：', { exact: false }).waitFor();
  check(state.optionsRefs.at(-1) === 'BD-TEST-PARTIAL', '代录弹窗按订单号读取退款项');
  check(await page.getByText('部分退款', { exact: true }).first().isVisible(), '订单摘要展示状态');

  // 未选行时提交禁用；勾选一行可用行 + 一行已被使用行后可提交
  await page.getByRole('button', { name: '部分退款', exact: true }).click();
  await page.getByRole('checkbox', { name: '选择退款行 1' }).waitFor();
  check(await page.getByRole('checkbox', { name: '选择退款行 3' }).count() === 0, '已退款行不再渲染');
  check(await submitCreate.isDisabled(), '部分退款未选行不可提交');
  await page.getByRole('checkbox', { name: '选择退款行 1' }).check();
  await page.getByRole('checkbox', { name: '选择退款行 2' }).check();
  await page.getByPlaceholder(/代录\/协商金额/).fill('50');
  await page.getByPlaceholder(/申请事由/).fill('邮件协商退 line-1 与 line-2');
  check(await submitCreate.isEnabled(), '选行（含已被使用行）后可提交部分退款代录');
  await submitCreate.click();
  await page.getByText('已代录退款申请，请在列表中审批执行').waitFor();
  const created = state.createPayloads.at(-1);
  check(created.order_id === 'BD-TEST-PARTIAL', '代录提交携带订单号引用');
  check(created.refund_type === 'partial', '代录提交退款类型为部分退');
  check(
    Array.isArray(created.line_ids) && created.line_ids.length === 2
      && created.line_ids.includes('line-1') && created.line_ids.includes('line-2'),
    '代录提交携带所选行 line_ids（含已被使用的行）',
  );
  check(created.amount === 5000, '代录提交携带协商金额（分）');

  // ── 审批 r1：默认勾选作废；非法金额 / 缺调整理由被前端拦截；取消勾选提交 revoke_codes=false ──
  await page.getByRole('button', { name: '查看退款单 RF-TEST-1 详情' }).click();
  await page.getByRole('heading', { name: /退款单 RF-TEST-1/ }).waitFor();
  await page.getByRole('button', { name: /批准并执行/ }).click();
  const revokeCheckbox = page.getByRole('checkbox', { name: '退款后作废已选激活码' });
  await revokeCheckbox.waitFor();
  check(await revokeCheckbox.isChecked(), '审批弹窗默认勾选作废已选激活码');

  const amountInput = page.getByLabel('批准金额（元）');
  const confirmApprove = page.getByRole('button', { name: /确认批准并执行渠道退款/ });
  // 非法金额（abc）不能静默按 0 提交：按钮禁用 + 明确提示
  await amountInput.fill('abc');
  check(await confirmApprove.isDisabled(), '非法金额禁止提交批准');
  check(await page.getByText('请输入有效金额（元）').isVisible(), '非法金额给出明确错误提示');
  // 金额与申请额不一致（¥100 ≠ 申请 ¥150）必须填调整理由
  await amountInput.fill('100');
  check(await confirmApprove.isDisabled(), '下调金额未填理由禁止提交');
  check(await page.getByText('金额与申请额不一致，必须填写调整理由').isVisible(), '缺调整理由给出明确错误提示');
  await page.getByPlaceholder('审批意见 / 金额调整理由').fill('协商保留激活码并下调金额');
  check(await confirmApprove.isEnabled(), '填写调整理由后可提交下调金额');

  // 取消作废勾选：提示行锁定但码保留，提交 revoke_codes=false
  await revokeCheckbox.uncheck();
  check(await page.getByText('退款行仍会锁定', { exact: false }).isVisible(), '取消作废时提示行锁定但码保留');
  await confirmApprove.click();
  await page.getByText(/已批准并执行/).waitFor();
  check(
    state.approvePayloads.length === 1
      && state.approvePayloads[0].id === 'r1'
      && state.approvePayloads[0].revoke_codes === false
      && state.approvePayloads[0].approved_amount === 10000,
    '取消作废后 approve 提交 revoke_codes=false 与调整后金额',
  );

  // ── 审批 r2：保持默认勾选直接批准，提交 revoke_codes=true ──
  await page.getByRole('button', { name: '查看退款单 RF-TEST-2 详情' }).click();
  await page.getByRole('heading', { name: /退款单 RF-TEST-2/ }).waitFor();
  await page.getByRole('button', { name: /批准并执行/ }).click();
  const revokeCheckbox2 = page.getByRole('checkbox', { name: '退款后作废已选激活码' });
  await revokeCheckbox2.waitFor();
  check(await revokeCheckbox2.isChecked(), '重新打开详情后作废勾选重置为默认勾选');
  await page.getByRole('button', { name: /确认批准并执行渠道退款/ }).click();
  await page.getByRole('heading', { name: /退款单 RF-TEST-2/ }).waitFor({ state: 'detached' });
  check(
    state.approvePayloads.length === 2
      && state.approvePayloads[1].id === 'r2'
      && state.approvePayloads[1].revoke_codes === true
      && state.approvePayloads[1].approved_amount === 30000,
    '保持默认勾选 approve 提交 revoke_codes=true 与申请额',
  );
}
