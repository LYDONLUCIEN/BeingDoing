/** 测试中心 UI 的受控接口和操作验收；后端鉴权/隔离另由 API 套件验证。 */
export async function prepareAdmin(context) {
  const user = { user_id: 'center-browser-test', username: '测试管理员', is_super_admin: true, email_verified: true };
  await context.addInitScript(user => localStorage.setItem('auth-storage', JSON.stringify({ state: { user, token: 'fixture-token', isAuthenticated: true }, version: 0 })), user);
  const definition = { title: '浏览器验收示例', module: '测试中心', kind: 'api', inputs: ['用户执行创建'], assertions: ['状态为已创建'], targets: ['test/backend/test_sample.py'], timeout: 30 };
  definition.purpose = '保护已经确认的产品规则';
  definition.sources = [{ path: 'docs/PRODUCT_RULES.md', rule: '固定的产品规则' }];
  const test = { id: 'sample', revision: 'browser-fixed-revision', definition, core: true, archived: false, available: true, version: true };
  const build = { sha: 'fixture-source', label: '测试版本 · 开发中', dirty: true, tag: '', base_tag: '' };
  const runs = []; const cases = [test]; const drafts = []; const contexts = [];
  const versions = new Map();

  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url()); const endpoint = url.pathname; let data = {};
    if (endpoint.endsWith('/auth/me')) data = user;
    else if (endpoint.endsWith('/test-center/catalog')) data = { cases, build, changes: [], coverage_gaps: [], unknown_cases: [], worker: { ready: true } };
    else if (endpoint.endsWith('/test-center/capabilities')) data = { configured: true, worker_key_ready: true, config: { provider: 'fixture', chat: { model: 'fixture-chat' }, rumination: { model: 'fixture-v4' } } };
    else if (endpoint.endsWith('/test-center/contexts')) {
      if (route.request().method() === 'POST') { const spec = route.request().postDataJSON(); data = { id: `ctx-${contexts.length}`, created: Date.now()/1000, spec, version: 1 }; contexts.push(data); }
      else data = contexts;
    }
    else if (endpoint.endsWith('/test-center/drafts')) {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON(); const invalid = body.assertions.includes('尚未实现的任意要求');
        data = { id: `draft-${drafts.length}`, created: Date.now()/1000, base_revision: body.base_revision,
          state: invalid ? 'needs_clarification' : 'ready', issues: invalid ? ['未支持的断言：尚未实现的任意要求'] : [],
          definition: { ...definition, ...body, id: body.case_id || `custom-${drafts.length}`, origin: 'authored', module: '管理员用例', targets: body.kind === 'ai' ? ['ai-replay'] : definition.targets } };
        drafts.push(data);
      } else data = drafts;
    }
    else if (endpoint.endsWith('/test-center/cases') && route.request().method() === 'POST') {
      const draft = drafts.find(d => d.id === route.request().postDataJSON().draft_id);
      if (!draft || draft.state !== 'ready') throw new Error('不能保存未实现草稿');
      data = { id: draft.definition.id, revision: `revision-${draft.id}` };
      const item = { ...test, ...data, core: false, definition: draft.definition };
      const existing = cases.findIndex(c => c.id === data.id); if (existing < 0) cases.push(item); else cases[existing] = item;
      versions.set(data.id, [...(versions.get(data.id) || []), { revision: data.revision, definition: item.definition }]);
    }
    else if (endpoint.endsWith('/revisions')) data = versions.get(endpoint.split('/').at(-2)) || [];
    else if (endpoint.endsWith('/reviews')) {
      const run = runs.find(r => r.id === endpoint.split('/').at(-2));
      data = { ...route.request().postDataJSON(), id: 'review-fixture', created: Date.now()/1000, reviewer: '浏览器测试管理员' };
      run.reviews.push(data);
    }
    else if (endpoint.endsWith('/test-center/cases/sample')) { Object.assign(test, route.request().postDataJSON()); data = test; }
    else if (endpoint.endsWith('/test-center/runs') && route.request().method() === 'POST') {
      const request = route.request().postDataJSON();
      if (request.case_ids.some(id => !cases.some(c => c.id === id)) || request.mode !== 'diagnostic') throw new Error('界面提交的选择不正确');
      const chosen = cases.filter(c => request.case_ids.includes(c.id));
      const ai = chosen.some(c => c.definition.kind === 'ai');
      const run = { id: `fixture-${runs.length}`, status: ai ? 'needs_review' : 'fail', mode: 'diagnostic', created: Date.now()/1000, build, reviews: [],
        cases: chosen.map(c => ({ ...c, status: ai ? 'needs_review' : 'fail', error: ai ? null : '用于验收的明确失败', artifacts: [], counts: { tests: 1, failures: ai ? 0 : 1, needs_review: ai ? 1 : 0, planned: 1 },
          ...(c.definition.kind === 'ai' ? { attempts: [{ index: 0, input_index: 0, repeat: 1, input: c.definition.inputs[0], reply: '可以讲讲最近的一次经历吗？', raw_reply: '可以讲讲最近的一次经历吗？', status: 'needs_review', checks: [{ index: 0, status: 'needs_review', reason: '需要人工判断语义' }], context_id: c.definition.context_id, prompt_digest: 'fixture-prompt', actual_model: 'fixture-v4', messages: [{ role: 'user', content: c.definition.inputs[0] }], ...(c.definition.conversation_mode === 'workflow' ? { prompt_digest: undefined, request: { method: 'PATCH', path: '/api/v1/simple-chat/rumination-v4/combos/combo_1/conclusion-card', body: { hypothesis: '写一本书' } }, http_status: 200, before_state: { combo: { conclusion_card: { hypothesis: '' } } }, state: { combo: { conclusion_card: { hypothesis: '写一本书' } } }, model_calls: [] } : {}) }] } : {}) })),
        ...(ai ? { ai: { planned_calls: 2, budget: request.budget }, usage: { calls: 2, total_tokens: 200, charged_tokens: 200, unknown_calls: 0, cost: null } } : {}) };
      if (ai && request.budget?.max_calls !== 4) throw new Error('未提交 AI 批次预算');
      runs.unshift(run); data = run;
    } else if (endpoint.endsWith('/test-center/runs')) data = runs;
    else if (endpoint.includes('/test-center/runs/')) data = runs.find(run => endpoint.endsWith(run.id));
    await route.fulfill({ json: { code: 200, message: 'ok', data } });
  });
  return { test, runs, cases, drafts, contexts };
}

export async function testAdmin(page, base, state, check) {
  await page.goto(`${base}/admin/test-center`, { waitUntil: 'networkidle' });
  await page.getByTestId('test-center').waitFor();
  await page.getByText('浏览器验收示例', { exact: true }).waitFor();
  check(await page.getByRole('button', { name: /运行完整发布验收/ }).isDisabled(), '开发中不允许发布验收');
  await page.getByText('查看输入与断言', { exact: false }).click();
  check(await page.getByText('用户执行创建', { exact: true }).isVisible(), '输入独立展示');
  check(await page.getByText('状态为已创建', { exact: true }).isVisible(), '断言独立展示');
  check(await page.getByText('保护已经确认的产品规则', { exact: true }).isVisible(), '测试目的可见');
  check(await page.getByText(/依据：docs\/PRODUCT_RULES.md/).isVisible(), '用例可追溯到规范来源');
  await page.getByRole('checkbox', { name: '选择 浏览器验收示例' }).check();
  await page.getByRole('button', { name: '运行已选（1）' }).click();
  await page.getByText('用于验收的明确失败', { exact: true }).waitFor();
  check(state.runs.length === 1, '勾选只提交一次批次');
  await page.getByRole('button', { name: '失败 / 未完成项重跑' }).click();
  await page.waitForFunction(() => document.querySelectorAll('button').length > 0);
  await page.getByText('批次 fixture-', { exact: false }).waitFor();
  // 等待提交请求完成，而非等待任意固定时长。
  await page.waitForResponse(response => response.url().endsWith('/test-center/runs') && response.request().method() === 'GET').catch(() => {});
  check(state.runs.length === 2 && state.runs.every(run => run.status === 'fail'), '重跑保留首次失败');
  await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/test-center/runs') && response.request().method() === 'POST'),
    page.getByRole('button', { name: '一键核心回归', exact: true }).click(),
  ]);
  check(state.runs.length === 3 && state.runs[0].cases.length === 1, '一键核心回归自动选取核心用例');
  await page.getByRole('button', { name: '取消常驻', exact: true }).click();
  await page.getByRole('button', { name: '设为常驻', exact: true }).waitFor();
  check(!state.test.core, '管理员常驻选择已保存');
  await page.getByRole('button', { name: '归档', exact: true }).click();
  await page.getByText('当前筛选下没有用例。').waitFor();
  await page.getByRole('checkbox', { name: '显示归档' }).check();
  await page.getByRole('button', { name: '恢复', exact: true }).waitFor();
  check(await page.getByRole('checkbox', { name: '选择 浏览器验收示例' }).isDisabled(), '归档用例不能执行');
  await page.getByRole('button', { name: '恢复', exact: true }).click();
  await page.getByRole('button', { name: '归档', exact: true }).waitFor();
  check(!state.test.archived, '可以恢复用例');
  await testAuthoring(page, state, check);
  await testWorkflowAuthoring(page, state, check);
}


export async function testAuthoring(page, state, check) {
  await page.getByRole('button', { name: '编写新用例' }).click();
  const editor = page.getByTestId('case-editor');
  await editor.getByLabel('用例名称', { exact: true }).fill('编辑器生成的 API 检查');
  await editor.getByLabel('编辑测试类型').selectOption('api');
  await editor.getByLabel('动作模板').selectOption('sample');
  check(await editor.getByLabel('编辑用户输入').inputValue() === '用户执行创建', '模板输入与断言分别填充');
  await editor.getByLabel('编辑断言标准').fill('尚未实现的任意要求');
  await editor.getByRole('button', { name: '生成固定草稿' }).click();
  await editor.getByText('待澄清：这些要求尚不能执行').waitFor();
  check(await editor.getByRole('button', { name: '确认并保存用例' }).isDisabled(), '未知断言不能保存为可执行用例');
  await editor.getByLabel('编辑断言标准').fill('状态为已创建');
  await editor.getByRole('button', { name: '生成固定草稿' }).click();
  await editor.getByText('草稿可执行，请核对后保存').waitFor();
  await editor.getByRole('button', { name: '确认并保存用例' }).click();
  await page.getByRole('checkbox', { name: '选择 编辑器生成的 API 检查' }).waitFor();
  check(state.cases.length === 2 && state.drafts.length === 2, '草稿保存为固定用例，待澄清草稿保留');
  await editor.getByRole('button', { name: '关闭编辑器' }).click();
  await page.getByRole('button', { name: '编写新用例' }).click();
  await editor.getByLabel('用例名称', { exact: true }).fill('独立组合 AI 检查');
  await editor.getByLabel('测试目的', { exact: true }).fill('观察连续追问是否承接用户经历');
  await editor.getByLabel('编辑测试类型').selectOption('ai');
  await editor.getByLabel('对话方式', { exact: true }).selectOption('sequence');
  await editor.getByText('新建 AI 上下文起点', { exact: true }).click();
  await editor.getByLabel('保存点名称', { exact: true }).fill('组合一的起点');
  await editor.getByLabel('组合热爱').fill('写作');
  await editor.getByLabel('组合优势').fill('表达');
  await editor.getByLabel('用户背景', { exact: true }).fill('测试用虚构背景');
  await editor.getByLabel('包含业务状态起点').check();
  await editor.getByLabel('业务状态起点 JSON').fill(JSON.stringify({ completed_phases: ['values', 'strengths', 'interests', 'purpose'], basic_info: {}, conclusions: {}, thread_metadata: {}, anchor: {} }));
  await editor.getByLabel('已检查并脱敏这些背景与历史，适合发送到测试模型').check();
  await editor.getByRole('button', { name: '保存上下文起点' }).click();
  await editor.getByText('上下文已保存并选中').waitFor();
  check(state.contexts.length === 1, '独立组合上下文保存并选中');
  await editor.getByLabel('编辑用户输入').fill('我担心自己坚持不下去');
  await editor.getByLabel('编辑断言标准').fill('语义：询问一个具体经历');
  await editor.getByRole('button', { name: '生成固定草稿' }).click();
  await editor.getByText('草稿可执行，请核对后保存').waitFor();
  await editor.getByRole('button', { name: '确认并保存用例' }).click();
  await page.getByRole('checkbox', { name: '选择 独立组合 AI 检查' }).waitFor();
  check(state.cases.at(-1).definition.conversation_mode === 'sequence' && state.cases.at(-1).definition.purpose === '观察连续追问是否承接用户经历', '保存多轮模式与测试目的');
  await editor.getByRole('button', { name: '关闭编辑器' }).click();
  await page.getByRole('button', { name: '清空选择', exact: true }).click();
  await page.getByRole('checkbox', { name: '选择 独立组合 AI 检查' }).check();
  await page.getByLabel('AI 调用预算').fill('4');
  await page.getByLabel('AI token 预算').fill('100000');
  await page.getByRole('button', { name: '运行已选（1）' }).click();
  await page.getByText('追加人工复核', { exact: true }).waitFor();
  await page.getByText('输入 1 · 第 1 次 · 自动判定：待复核', { exact: true }).click();
  check(await page.getByText('可以讲讲最近的一次经历吗？', { exact: true }).isVisible(), '逐次结果展示本轮真实回复');
  await page.getByLabel('复核结论').selectOption('pass');
  await page.getByLabel('复核依据').fill('人工核对：一个问题，符合标准');
  await page.getByRole('button', { name: '保存复核记录' }).click();
  await page.getByText(/浏览器测试管理员.*人工核对：一个问题/).waitFor();
  check(state.runs[0].status === 'needs_review' && state.runs[0].reviews.length === 1, '人工复核追加记录，自动结果保持不变');
}

export async function testWorkflowAuthoring(page, state, check) {
  await page.getByRole('button', { name: '编写新用例' }).click();
  const editor = page.getByTestId('case-editor');
  await editor.getByLabel('用例名称', { exact: true }).fill('现有接口业务回放');
  await editor.getByLabel('编辑测试类型').selectOption('ai');
  await editor.getByLabel('对话方式', { exact: true }).selectOption('workflow');
  await editor.getByLabel('保存的上下文', { exact: true }).selectOption('ctx-0');
  await editor.getByLabel('编辑用户输入').fill('填写结论：写一本书');
  await editor.getByLabel('编辑断言标准').fill('第1步：结论包含：写一本书');
  await editor.getByRole('button', { name: '生成固定草稿' }).click();
  await editor.getByText('草稿可执行，请核对后保存').waitFor();
  await editor.getByRole('button', { name: '确认并保存用例' }).click();
  await page.getByRole('checkbox', { name: '选择 现有接口业务回放' }).waitFor();
  check(state.cases.at(-1).definition.conversation_mode === 'workflow', '业务回放模式固定保存');
  check(state.contexts[0].spec.workflow_seed.completed_phases.length === 4, '结构化前置状态与消息共同保存');
  await editor.getByRole('button', { name: '关闭编辑器' }).click();
  await page.getByRole('button', { name: '清空选择', exact: true }).click();
  await page.getByRole('checkbox', { name: '选择 现有接口业务回放' }).check();
  check(await page.getByText(/含业务回放：入队时按步骤估算/).isVisible(), '业务预算文案不谎称每步只调用一次');
  await page.getByRole('button', { name: '运行已选（1）' }).click();
  const summary = page.getByText('输入 1 · 第 1 次 · 自动判定：待复核', { exact: true });
  await page.getByText('业务步骤证据 · HTTP 200', { exact: true }).waitFor({ state: 'attached' });
  if (!await summary.evaluate(el => el.parentElement.open)) await summary.click();
  await page.getByText('业务步骤证据 · HTTP 200', { exact: true }).click();
  check(await page.getByText(/本步骤模型调用 0 次/).isVisible(), '非模型业务操作无需伪造模型提示词摘要');
  check(await page.locator('pre').filter({ hasText: 'before_state' }).filter({ hasText: '写一本书' }).isVisible(), '结果展示请求和操作前后状态');
}
