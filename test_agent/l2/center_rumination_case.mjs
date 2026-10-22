/** 真页面 + 受控 API 验证 v4 首开引导、选点、组合隔离、填写与终选，不调用模型。 */
export async function prepareRumination(context) {
  const user = { user_id: 'v4-test', username: '沉淀测试', email_verified: true };
  await context.addInitScript(user => {
    localStorage.setItem('auth-storage', JSON.stringify({ state: { user, token: 'fixture', isAuthenticated: true }, version: 0 }));
    localStorage.setItem(`explore_user_survey_${user.user_id}`, '1');
    localStorage.setItem('explore_session_FIXTURE', JSON.stringify({ activationCode: 'FIXTURE', currentPhase: 'rumination', unlockedPhases: ['values', 'strengths', 'interests', 'purpose', 'rumination'], surveyCompleted: true }));
  }, user);
  const state = { schema_version: 4, matrix_snapshot: { passions: ['帮助他人', '创作'], strengths: ['倾听', '分析'] }, combo_sessions: [], active_combo_id: null, final_selection: { selected_combo_ids: [], submitted: false }, main_section: 'matrix', intro_shown: true };
  const fixture = { state, sent: [], release: null, submissions: 0, introMarks: 0, createRequests: [], legacyReportReady: false };
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url()); const endpoint = url.pathname;
    const body = route.request().method() === 'GET' ? {} : route.request().postDataJSON();
    let data = {};
    const id = endpoint.match(/\/combos\/([^/]+)/)?.[1];
    const combo = state.combo_sessions.find(c => c.combo_id === id);
    if (endpoint.endsWith('/auth/me')) data = user;
    else if (endpoint.endsWith('/rumination-v4/state')) data = { state, combos: state.combo_sessions, legacy_report_ready: fixture.legacyReportReady };
    else if (endpoint.endsWith('/rumination-v4/combos')) data = { combos: state.combo_sessions, active_combo_id: state.active_combo_id, legacy_report_ready: fixture.legacyReportReady };
    else if (endpoint.endsWith('/export/my-report-id')) data = { report_id: 'legacy-report', review_status: 'approved', recheck_status: null, recheck_used: false };
    else if (endpoint.endsWith('/intro-shown')) {
      fixture.introMarks++; state.intro_shown = true; data = { intro_shown: true };
    } else if (endpoint.endsWith('/create-and-start')) {
      fixture.createRequests.push(body);
      const item = { combo_id: `combo-${state.combo_sessions.length + 1}`, passion: body.passion, strengths: body.strengths, status: 'discussing', messages: [{ role: 'assistant', content: `探索${body.passion}的开场` }], conclusion_card: null, balance_analysis: null };
      state.combo_sessions.push(item); state.active_combo_id = item.combo_id;
      data = { combo_id: item.combo_id, combo: item, opening: item.messages[0] };
    } else if (endpoint.endsWith('/active')) {
      state.active_combo_id = body.combo_id; data = { active_combo_id: body.combo_id };
    } else if (endpoint.endsWith('/combo-chat')) {
      fixture.sent.push(body);
      await new Promise(resolve => { fixture.release = resolve; });
      await route.fulfill({ contentType: 'text/event-stream', body: 'data: {"chunk":"这是第一个组合的独立回复"}\n\ndata: {"done":true}\n\n' }); return;
    } else if (endpoint.endsWith('/conclusion-card/confirm')) {
      combo.status = 'concluded'; combo.balance_analysis = { status: 'done', balance_found: true, balance_fail_reason: null };
      await route.fulfill({ contentType: 'text/event-stream', body: 'data: {"analysis_status":"analyzing"}\n\ndata: {"analysis_done":{"balance_found":true,"balance_fail_reason":null}}\n\ndata: {"done":true}\n\n' }); return;
    } else if (endpoint.endsWith('/conclusion-card')) {
      combo.conclusion_card = { hypothesis: body.hypothesis, balance_found: null, balance_fail_reason: null, updated_at: new Date().toISOString() };
      data = { combo, conclusion_card: combo.conclusion_card };
    } else if (endpoint.endsWith('/final-selection/submit')) {
      fixture.submissions++; state.final_selection.submitted = true; data = { final_selection: state.final_selection, main_section: 'end' };
    } else if (endpoint.endsWith('/final-selection')) {
      state.final_selection.selected_combo_ids = body.selected_combo_ids; data = { final_selection: state.final_selection };
    } else if (combo) data = { combo };
    await route.fulfill({ json: { code: 200, message: 'ok', data } });
  });
  return fixture;
}

export async function testRumination(page, base, fixture, check, evidence) {
  const mobile = page.viewportSize().width < 768;
  fixture.legacyReportReady = true;
  await page.goto(`${base}/explore/chat/rumination?code=FIXTURE`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/\/explore\/report(?:\/view)?\?code=FIXTURE/);
  check(page.url().includes('/explore/report') && !page.url().includes('/explore/chat/rumination'), '严格识别的v3老报告直接收口到报告页');
  check(fixture.createRequests.length === 0, 'v3老报告收口不创建v4组合');
  fixture.legacyReportReady = false;
  fixture.state.intro_shown = false;
  await page.goto(`${base}/explore/chat/rumination?code=FIXTURE`, { waitUntil: 'networkidle' });
  const input = page.locator('textarea.flow-input-field');
  const start = page.getByRole('button', { name: /开始探索/ });
  const intro = page.getByRole('dialog', { name: '很高兴再次见到你！', exact: true });
  const guide = page.getByRole('status').filter({ hasText: '先创建一个新的组合' });
  const openList = async () => { const toggle = page.getByRole('button', { name: '打开组合列表' }); if (await toggle.isVisible()) await toggle.click(); };
  await intro.waitFor();
  check(!(await start.isVisible()), '首次进入未新建组合时不自动展示选择器');
  await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/intro-shown') && r.request().method() === 'POST'),
    intro.getByRole('button', { name: '确定', exact: true }).click(),
  ]);
  await intro.waitFor({ state: 'hidden' });
  check(fixture.introMarks === 1, '首次欢迎弹窗确认后持久化展示标记');
  check(!(await start.isVisible()), '确认欢迎弹窗后仍需主动新建组合');
  await page.screenshot({ path: `${evidence}-first-guide.png` });
  await guide.getByRole('button', { name: /新建组合/ }).click();
  await start.waitFor();
  check(await start.isVisible(), '对话引导卡新建组合后打开选择面板');
  check(fixture.createRequests.length === 0 && fixture.state.combo_sessions.length === 0, '新建组合只进入草稿，尚未创建组合');
  await page.reload({ waitUntil: 'networkidle' });
  await guide.waitFor();
  check(!(await intro.isVisible()) && fixture.introMarks === 1, '已标记的欢迎弹窗重进不重复出现');
  check(!(await start.isVisible()), '重进页面仍未主动新建时不展示选择器');
  await openList();
  await page.locator('.v4-combo-sidebar').getByRole('button', { name: '新建组合', exact: true }).click();
  await start.waitFor();
  check(await start.isVisible(), '左侧新建组合后打开选择面板');
  check(fixture.createRequests.length === 0 && fixture.state.combo_sessions.length === 0, '左侧新建同样只进入草稿');
  if (mobile) await page.screenshot({ path: `${evidence}-selection.png` });
  check(await input.isDisabled(), '未确认组合前禁止输入');
  const narrowSelector = page.getByRole('button', { name: '打开组合选择器', exact: true });
  check(await start.isDisabled(), '未选择热爱与优势不能开始');
  await page.getByRole('button', { name: '帮助他人', exact: true }).click();
  await page.getByRole('button', { name: '倾听', exact: true }).click();
  await page.getByRole('button', { name: '分析', exact: true }).click();
  await start.click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '探索帮助他人的开场' }).waitFor();
  check(await input.isEnabled(), '创建组合后对话可用');
  check(fixture.createRequests.length === 1 && fixture.createRequests[0].strengths.join() === '倾听,分析', '开始探索时才按原选点创建一热爱多优势组合');
  if (mobile) {
    const box = await input.boundingBox();
    check(box.width > page.viewportSize().width * .65, '沉淀输入区使用完整宽度');
  }
  await page.screenshot({ path: `${evidence}-chat.png` });
  // 真实点击手机抽屉/桌面侧栏，建立第二个独立组合。
  await openList();
  const newCombo = page.getByRole('button', { name: /新建组合/ });
  await newCombo.first().click();
  await page.getByRole('button', { name: '创作', exact: true }).click();
  await page.getByRole('button', { name: '分析', exact: true }).click();
  await start.click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '探索创作的开场' }).waitFor();
  await input.fill('仅第二组合的未发送草稿');
  if (mobile) {
    await page.getByRole('button', { name: '组合与结论', exact: true }).click();
    await page.locator('.conclusion-card-v4 textarea').fill('仅第二组合的结论草稿');
    await page.getByRole('button', { name: '对话', exact: true }).click();
    check(await input.inputValue() === '仅第二组合的未发送草稿', '切换面板保留未发送草稿');
  }
  await openList();
  await page.locator('.v4-combo-sidebar [role="button"], .combo-toolbar .combo-tab').filter({ hasText: '帮助他人' }).click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '探索帮助他人的开场' }).waitFor();
  check(await input.inputValue() === '', '未发送草稿不串入其他组合');
  if (mobile) {
    await page.getByRole('button', { name: '组合与结论', exact: true }).click();
    check(await page.locator('.conclusion-card-v4 textarea').inputValue() === '', '结论草稿不串入其他组合');
    await page.getByRole('button', { name: '对话', exact: true }).click();
  }
  await input.fill('输入法尚未完成');
  await input.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true });
  await page.waitForTimeout(100);
  check(fixture.sent.length === 0, '沉淀输入法选词不发送');
  await input.fill('继续探索第一个方向');
  await Promise.all([page.waitForRequest(r => r.url().endsWith('/combo-chat')), page.getByRole('button', { name: '发送', exact: true }).click()]);
  check(fixture.sent[0].combo_id === 'combo-1', '沉淀发送归属当前组合');
  await openList();
  await page.locator('.v4-combo-sidebar [role="button"], .combo-toolbar .combo-tab').filter({ hasText: '创作' }).click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '探索创作的开场' }).waitFor();
  check(await input.isDisabled(), '其他组合回复期间禁止并行发送');
  check(await input.inputValue() === '仅第二组合的未发送草稿', '返回组合恢复自己的未发送草稿');
  if (mobile) {
    await page.getByRole('button', { name: '组合与结论', exact: true }).click();
    check(await page.locator('.conclusion-card-v4 textarea').inputValue() === '仅第二组合的结论草稿', '返回组合恢复自己的结论草稿');
    await page.getByRole('button', { name: '对话', exact: true }).click();
  }
  fixture.release();
  await page.waitForFunction(() => !document.querySelector('textarea.flow-input-field').disabled);
  check(!(await page.locator('.flow-msg-ai-content').allTextContents()).join('').includes('第一个组合的独立回复'), '回复不串入第二组合');
  await openList();
  await page.locator('.v4-combo-sidebar [role="button"], .combo-toolbar .combo-tab').filter({ hasText: '帮助他人' }).click();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '探索帮助他人的开场' }).waitFor();
  await page.locator('.flow-msg-ai-content').filter({ hasText: '第一个组合的独立回复' }).waitFor();
  if (mobile) await page.getByRole('button', { name: '组合与结论', exact: true }).click();
  else {
    if (await narrowSelector.isVisible()) await narrowSelector.click();
    const expand = page.getByRole('button', { name: '展开组合选择器' });
    if (await expand.isVisible()) await expand.click();
  }
  await page.locator('.conclusion-card-v4 textarea').fill('帮助年轻人通过倾听找到职业方向');
  await page.locator('.conclusion-card-v4').getByRole('button', { name: '确认', exact: true }).click();
  await page.locator('.conclusion-card-v4').getByText('推荐', { exact: true }).waitFor();
  check(fixture.state.combo_sessions[0].conclusion_card.hypothesis === '帮助年轻人通过倾听找到职业方向', '假设方向按用户原文保存');
  const closeSelector = page.getByRole('button', { name: '关闭组合选择器', exact: true });
  if (await closeSelector.isVisible()) await closeSelector.click();
  await page.getByRole('button', { name: '完成并继续', exact: true }).click();
  await page.getByText('最终选择 1–3 个方向', { exact: true }).waitFor();
  const confirm = page.getByRole('button', { name: /^确认选择/ });
  check(await confirm.isDisabled(), '终选未选择方向前不能提交');
  await page.locator('.direction-grid').getByText('帮助年轻人通过倾听找到职业方向', { exact: true }).click();
  await page.screenshot({ path: `${evidence}-final.png` });
  await confirm.click();
  await page.waitForURL('**/explore/transition?from=rumination');
  check(fixture.submissions === 1 && fixture.state.final_selection.selected_combo_ids.join() === 'combo-1', '仅提交用户选择的方向一次');
}
