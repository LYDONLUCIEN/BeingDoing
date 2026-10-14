/** 前四阶段真实页面的流式门禁与会话归属；后端/模型使用受控边界。 */
export async function prepareChat(context, phase = 'values') {
  const user = { user_id: 'chat-browser-test', username: '交互测试', email_verified: true };
  await context.addInitScript(({ user, phase }) => {
    localStorage.setItem('auth-storage', JSON.stringify({ state: { user, token: 'fixture-token', isAuthenticated: true }, version: 0 }));
    localStorage.setItem(`explore_user_survey_${user.user_id}`, '1');
    localStorage.setItem('explore_session_FIXTURE', JSON.stringify({ activationCode: 'FIXTURE', currentPhase: phase, unlockedPhases: ['values', 'strengths', 'interests', 'purpose'], surveyCompleted: true }));
  }, { user, phase });
  const state = { phase, initCalls: 0, sent: null, release: null };
  const threads = ['one', 'two'].map((id, i) => ({ id, title: `测试会话${i+1}`, status: 'in-progress', createdAt: 1700000000000 + i }));
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url()); const endpoint = url.pathname; let data = {};
    if (endpoint.endsWith('/auth/me')) data = user;
    else if (endpoint.endsWith('/notifications')) data = { items: [], total: 0, unread_count: 0, page_size: 20 };
    else if (endpoint.endsWith('/simple-auth/journeys')) data = { journeys: [{ activation_code: 'FIXTURE', explore_resume: { resume_phase: phase, unlocked_phases: ['values', 'strengths', 'interests', 'purpose'], report_unlocked: false } }] };
    else if (endpoint.endsWith('/simple-chat/threads')) data = { threads, step_locked: false };
    else if (endpoint.endsWith('/simple-chat/history')) {
      const id = url.searchParams.get('thread_id');
      data = { messages: [{ role: 'assistant', content: id === 'one' ? '第一会话的开场' : '第二会话的独立开场' }], metadata: { thread_id: id, step_locked: false }, activation: { activation_session_id: 'activation-fixture' } };
    } else if (endpoint.endsWith('/simple-chat/init')) {
      state.initCalls += 1; data = { messages: [{ role: 'assistant', content: '新的会话已创建' }], activation: { activation_session_id: 'activation-fixture' } };
    } else if (endpoint.endsWith('/simple-chat/message/stream')) {
      state.sent = route.request().postDataJSON();
      await new Promise(resolve => { state.release = resolve; });
      await route.fulfill({ contentType: 'text/event-stream', body: 'data: {"chunk":"只属于第一会话的新回复"}\n\ndata: {"done":true}\n\n' });
      return;
    }
    await route.fulfill({ json: { code: 200, message: 'ok', data } });
  });
  return state;
}

export async function testChat(page, base, state, check) {
  await page.goto(`${base}/explore/chat/${state.phase}?code=FIXTURE&thread_id=one`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: '开始探索', exact: true }).click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '第一会话的开场' }).waitFor();
  const mobile = page.viewportSize().width < 768;
  const openThreads = async () => {
    if (mobile) await page.getByRole('button', { name: '打开会话列表', exact: true }).click();
  };
  const closeThreads = async () => {
    if (mobile) await page.getByRole('button', { name: '关闭会话列表', exact: true }).click();
  };
  if (mobile) {
    const input = await page.locator('textarea.flow-input-field').boundingBox();
    check(input.width > page.viewportSize().width * 0.65, '手机输入区使用完整宽度');
    const title = await page.locator('.careering-chat-phase-title').boundingBox();
    const toggle = await page.getByRole('button', { name: '打开会话列表' }).boundingBox();
    check(title.x >= toggle.x + toggle.width, '阶段标题不会被抽屉按钮遮挡');
    check(!await page.locator('.ol-msg-launcher--chat').isVisible(), '反馈浮层不遮挡聊天操作');
    await page.getByRole('button', { name: '打开导航菜单' }).click();
    await page.locator('#mobile-navigation').getByRole('button', { name: '站内信与反馈', exact: true }).click();
    const feedback = page.getByRole('dialog', { name: '站内信与反馈', exact: true });
    await feedback.waitFor();
    check(await feedback.isVisible(), '手机顶栏仍可打开反馈与站内信');
    await feedback.getByRole('button', { name: '关闭', exact: true }).click();
    await openThreads();
    await page.keyboard.press('Escape');
    check(!await page.getByRole('dialog', { name: '会话列表' }).isVisible(), 'Escape 关闭会话抽屉');
  }
  await openThreads();
  const create = page.locator('.careering-sidebar-header button').first();
  check(await create.isEnabled(), '静止时允许新建');
  await closeThreads();
  await page.locator('textarea.flow-input-field').fill('中文输入尚未选词');
  await page.locator('textarea.flow-input-field').dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true, keyCode: 13 });
  await page.locator('textarea.flow-input-field').dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: false, keyCode: 229 });
  await page.waitForTimeout(100);
  check(state.sent === null, '输入法确认候选词不会提交消息');
  await page.locator('textarea.flow-input-field').fill('请帮助我继续探索');
  await Promise.all([
    page.waitForRequest(r => r.url().endsWith('/simple-chat/message/stream')),
    page.locator('.flow-send-btn').click(),
  ]);
  await openThreads();
  check(await create.isDisabled(), '流式期间新建被禁用');
  check(state.initCalls === 0, '禁用期间未产生新建接口调用');
  check(state.sent?.thread_id === 'one', '发送归属当前会话');
  await closeThreads();
  state.release();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '只属于第一会话的新回复' }).waitFor();
  await page.waitForFunction(() => !document.querySelector('.flow-send-btn.is-stop'));
  await openThreads();
  check(await create.isEnabled(), '结束后恢复新建');
  await page.getByText('第二会话的独立开场', { exact: true }).click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '第二会话的独立开场' }).waitFor();
  check(!(await page.locator('.flow-msg-ai-content').allTextContents()).join('').includes('只属于第一会话'), '第二会话不展示第一会话回复');
  await openThreads();
  await create.click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '新的会话已创建' }).waitFor();
  check(state.initCalls === 1, '恢复后恰好新建一次');
  if (mobile) {
    check(!await page.getByRole('dialog', { name: '会话列表' }).isVisible(), '新建后自动回到对话');
    await page.setViewportSize({ width: page.viewportSize().width, height: 480 });
    await page.locator('textarea.flow-input-field').focus();
    await page.waitForFunction(() => {
      const r = document.querySelector('.flow-send-btn').getBoundingClientRect();
      return r.bottom <= innerHeight && r.top >= 0;
    });
    check(true, '缩小可视高度后发送按钮仍可见');
    const size = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
    check(size.scroll <= size.width + 1, '聊天页面不横向溢出');
  }
}
