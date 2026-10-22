/** 注册、个人空间、报告及支付的浏览器契约测试；不发送邮件、不生成真实订单。 */
export async function prepareAccount(context) {
  const user = { user_id: 'mobile-account', username: '手机测试', email: 'mobile@example.invalid', email_verified: true, token: 'fixture' };
  const phaseKeys = ['values', 'strengths', 'interests', 'purpose', 'rumination'];
  const state = { register: null, creates: [], cancelled: 0, downloads: [], review: 'approved', granted: false };
  const order = { id: 'order-fixture', order_no: 'TEST-ORDER', product_type: 'quarterly_package', status: 'pending', amount_original: 5900, amount_paid: 5900, created_at: '2026-10-14T00:00:00Z', channel: 'alipay', meta: {} };
  const deliveredOrder = { ...order, status: 'granted', delivered_code: 'OPENLIFE-GGGG-HHHH-IIII' };
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url()); const p = url.pathname;
    const body = route.request().method() === 'GET' ? {} : route.request().postDataJSON(); let data = {};
    if (p.endsWith('/auth/register/code')) data = { pending_id: 'pending-fixture' };
    else if (p.endsWith('/auth/register/verify')) {
      if (body.code !== '123456') { await route.fulfill({ status: 400, json: { detail: '验证码错误或已过期' } }); return; }
      data = { ticket: 'verified-ticket' };
    } else if (p.endsWith('/auth/register/poll')) data = { verified: false };
    else if (p.endsWith('/auth/register')) { state.register = body; data = user; }
    else if (p.endsWith('/auth/me')) data = user;
    else if (p.endsWith('/analytics/likes')) data = { records: [], total: 0 };
    else if (p.endsWith('/notifications')) data = { items: [], total: 0 };
    else if (p.endsWith('/simple-auth/journeys')) data = { journeys: [
      { activation_code: 'OPENLIFE-AAAA-BBBB-CCCC', code_type: 'trial', status: 'active', created_at: '2026-10-14T00:00:00Z', explore_resume: { resume_phase: 'values', unlocked_phases: ['values'], report_unlocked: false } },
      { activation_code: 'OPENLIFE-DDDD-EEEE-FFFF', code_type: 'full', status: 'active', created_at: '2026-10-13T00:00:00Z', explore_resume: { resume_phase: 'rumination', unlocked_phases: phaseKeys, report_unlocked: true } },
    ] };
    else if (p.endsWith('/simple-auth/my-codes')) data = { items: [{ code: 'OPENLIFE-AAAA-BBBB-CCCC', code_type: 'trial', status: 'active', has_report: false }] };
    else if (p.endsWith('/simple-auth/my-purchased-codes')) data = { items: [] };
    else if (p.endsWith('/payment/my-coupons')) data = { available: [], used: [], expired: [] };
    else if (p.endsWith('/payment/products')) data = { items: [{ product_type: 'quarterly_package', name: '启程版', amount: 5900 }, { product_type: 'annual_package', name: '远航版', amount: 12800 }] };
    else if (p.endsWith('/payment/orders') && route.request().method() === 'POST') {
      state.creates.push(body); data = { order, payment: { pay_type: 'qr', pay_url: 'https://example.invalid/test-cashier', qr_text: 'fixture-payment-only' } };
    } else if (p.endsWith('/payment/orders')) data = { items: [state.granted ? deliveredOrder : order], total: 1, page: 1, page_size: 20 };
    else if (p.endsWith('/order-fixture/cancel')) { state.cancelled++; data = { order: { ...order, status: 'cancelled' } }; }
    else if (p.includes('/payment/orders/')) data = { order: state.granted ? deliveredOrder : order, pay_type: 'qr', qr_text: 'fixture-payment-only', pay_url: 'https://example.invalid/test-cashier' };
    else if (p.endsWith('/export/my-report-id')) data = { report_id: 'report-fixture', review_status: state.review, review_deadline: '2099-10-14T00:00:00Z' };
    else if (p.includes('/export/report-pdf-status/')) { await route.fulfill({ json: { status: 'ready' } }); return; }
    else if (p.includes('/export/report-pdf-download/')) {
      state.downloads.push(url.searchParams.get('activation_code'));
      // 有效的极小 PDF，用于检验下载链路，不代表真实报告渲染验收。
      const objects = ['1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n', '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n', '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>\nendobj\n'];
      let pdf = '%PDF-1.4\n'; const offsets = [0];
      for (const object of objects) { offsets.push(Buffer.byteLength(pdf)); pdf += object; }
      const xref = Buffer.byteLength(pdf);
      pdf += `xref\n0 4\n0000000000 65535 f \n${offsets.slice(1).map(n => `${String(n).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
      await route.fulfill({ contentType: 'application/pdf', headers: { 'content-disposition': 'attachment; filename="mobile-test.pdf"' }, body: pdf }); return;
    }
    await route.fulfill({ json: { code: 200, message: 'ok', data } });
  });
  return state;
}

async function checkWidth(page, check, label) {
  const size = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
  check(size.content <= size.viewport + 1, `${label}不横向溢出 (${size.content}/${size.viewport})`);
}

export async function testAccount(page, base, state, check, replacePage) {
  await page.goto(`${base}/auth/register`, { waitUntil: 'networkidle' });
  await page.getByLabel('邮箱', { exact: true }).fill('mobile@example.invalid');
  await page.getByRole('button', { name: '发送验证码', exact: true }).click();
  await page.getByLabel('邮箱验证码', { exact: true }).fill('000000');
  await page.getByRole('button', { name: '验证并继续', exact: true }).click();
  await page.getByText('验证码错误或已过期', { exact: true }).waitFor();
  check(state.register === null, '错误验证码不能建号');
  await page.getByLabel('邮箱验证码', { exact: true }).fill('123456');
  await page.getByRole('button', { name: '验证并继续', exact: true }).click();
  await page.getByLabel('密码', { exact: true }).fill('fixture-password');
  await page.getByLabel('确认密码', { exact: true }).fill('fixture-password');
  await page.getByRole('button', { name: '完成注册', exact: true }).click();
  await page.getByText('请阅读并同意协议后继续', { exact: true }).waitFor();
  check(state.register === null, '未同意协议不能注册');
  await checkWidth(page, check, '注册');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: '完成注册', exact: true }).click();
  await page.waitForURL('**/explore');
  check(state.register?.ticket === 'verified-ticket', '注册携带验证凭证');

  // 注册已验证，后续从同一登录会话的新页面进入，避免探首页二次导航打断后续用例。
  page = await replacePage();
  await page.goto(`${base}/dashboard`, { waitUntil: 'networkidle' });
  await page.locator('.ol-profile-journey-card').first().waitFor();
  const first = page.locator('.ol-profile-journey-card').first();
  check(await first.getByRole('button', { name: '报告', exact: true }).isDisabled(), '未完成旅程的报告不能访问');
  check(await first.locator('.ol-stage-mark:disabled').count() === 4, '未解锁的四个阶段保持禁用');
  await checkWidth(page, check, '个人空间');
  const purchaseCard = page.locator('.ol-profile-purchase-card');
  const purchaseCardText = await purchaseCard.innerText();
  check(['免费版', '启程版', '远航版'].every(name => purchaseCardText.includes(name)), '个人空间购买入口同步展示免费版、启程版、远航版');
  check(!purchaseCardText.includes('季度套餐') && !purchaseCardText.includes('年度套餐'), '个人空间购买入口不再使用季度/年度旧名称');
  await purchaseCard.getByRole('button', { name: '立即购买', exact: true }).click();
  await page.getByText('选择适合你的探索方式', { exact: true }).waitFor();
  check(await page.locator('input[name="purchase-plan"][value="quarterly_package"]').isChecked(), '购买弹窗默认选择启程版');
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({ state: 'detached' });
  await page.locator('.ol-profile-journey-card').last().getByRole('button', { name: '报告', exact: true }).click();
  await page.waitForURL('**/explore/report/view**');
  const downloadButton = page.getByRole('button', { name: /下载.*PDF|下载报告/ });
  await downloadButton.waitFor();
  const [download] = await Promise.all([page.waitForEvent('download'), downloadButton.click()]);
  check(await download.failure() === null && download.suggestedFilename() === 'mobile-test.pdf', '已审核报告可下载 PDF');
  check(state.downloads.join() === 'OPENLIFE-DDDD-EEEE-FFFF', '下载使用所选旅程的激活码');
  await checkWidth(page, check, '报告');
  state.review = 'pending_review';
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByText(/审核中/).first().waitFor();
  check(await downloadButton.count() === 0, '审核中不提供下载按钮');

  await page.goto(`${base}/dashboard/codes`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '购买激活码', exact: true }).click();
  await page.getByText('选择适合你的探索方式', { exact: true }).waitFor();
  check(state.creates.length === 0, '打开支付界面不会创建订单');
  await checkWidth(page, check, '购买弹窗');
  check(await page.getByRole('button', { name: /微信支付/ }).isDisabled(), '微信支付保持未开放');
  await page.getByRole('button', { name: '同意协议', exact: true }).click();
  await page.getByText(/订单 TEST-ORDER 已创建/).waitFor();
  check(state.creates.length === 1 && state.creates[0].channel === 'alipay' && state.creates[0].product_type === 'quarterly_package', '同意协议后按默认启程版使用既有支付宝渠道下单一次');
  await page.keyboard.press('Escape');
  await page.getByText('取消这笔订单？', { exact: true }).waitFor();
  check(await page.getByRole('button', { name: '继续支付', exact: true }).last().isVisible(), '等待支付关闭时可继续');
  await page.getByRole('button', { name: '暂不取消，先离开', exact: true }).click();
  check(state.cancelled === 0, '离开保留订单');
  await page.getByRole('button', { name: '订单记录', exact: true }).click();
  await page.getByRole('button', { name: '继续支付', exact: true }).click();
  await page.getByText(/订单 TEST-ORDER 已创建/).waitFor();
  check(state.creates.length === 1, '继续支付沿用原订单');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '取消订单', exact: true }).last().click();
  await page.waitForFunction(() => !document.body.textContent.includes('取消这笔订单？'));
  check(state.cancelled === 1, '显式取消才请求取消订单');
  state.granted = true;
  await page.goto(`${base}/payment/result?out_trade_no=TEST-ORDER`, { waitUntil: 'networkidle' });
  await page.getByText('OPENLIFE-GGGG-HHHH-IIII', { exact: true }).waitFor();
  check(true, '回跳页面根据服务端交付状态展示激活码');
  await checkWidth(page, check, '支付结果');

  await page.goto(`${base}/dashboard/codes?tab=orders`, { waitUntil: 'networkidle' });
  await page.getByText('OPENLIFE-GGGG-HHHH-IIII', { exact: true }).first().waitFor();
  check(await page.getByRole('button', { name: '申请退款', exact: true }).count() === 0, '已交付订单不展示申请退款入口');

  await page.goto(`${base}/dashboard/settings`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '修改密码', exact: true }).waitFor();
  check(await page.getByRole('button', { name: '注销账户', exact: true }).count() === 0, '设置页不展示注销账户入口');
  check(!(await page.getByText('危险区', { exact: true }).isVisible()), '设置页隐藏注销危险区');
}
