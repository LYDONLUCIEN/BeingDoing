/* guided 布局验证：拦截 state 接口把 submitted 改 false，验证三栏结构 + 新建组合锁屏 */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join('/home/gitclone/BeingDoing/test_agent/l2/node_modules', 'playwright'));

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', args: ['--no-sandbox'] });
  const token = fs.readFileSync('/tmp/.smoke_token3', 'utf8').trim();
  const uid = 'b8c4f12a-1625-4a63-aff3-2d2013182608';
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(({ tk, u }) => {
    localStorage.setItem('token', tk);
    localStorage.setItem(`explore_user_survey_${u}`, '1');
    localStorage.setItem(`explore_user_privacy_ack_${u}`, '1');
    localStorage.setItem('auth-storage', JSON.stringify({
      state: { user: { user_id: u, email: 'g@example.com', phone: null, username: 'g', avatar_url: null, is_super_admin: false, email_verified: true }, token: tk, isAuthenticated: true, recoveryMode: false }, version: 0,
    }));
    // 外观预设为 guided
    localStorage.setItem('openlife-chat-appearance', JSON.stringify({
      state: { ruminationLayout: 'guided' }, version: 1,
    }));
  }, { tk: token, u: uid });
  const page = await context.newPage();
  // 拦截 v4 state：取消提交锁定 + 跳过 intro
  await page.route('**/api/v1/simple-chat/rumination-v4/state*', async (route) => {
    const resp = await route.fetch();
    const json = await resp.json();
    if (json?.data?.state) {
      json.data.state.final_selection = { ...(json.data.state.final_selection || {}), submitted: false };
      json.data.state.intro_shown = true;
    }
    await route.fulfill({ response: resp, json });
  });

  await page.goto('http://127.0.0.1:3000/explore/chat/rumination?code=XV1F9OFYQ1', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3500);

  const layout = await page.evaluate(() => ({
    isGuided: document.querySelector('.rumination-v4-root')?.getAttribute('data-rumination-layout'),
    hasSidebar: !!document.querySelector('.v4-combo-sidebar'),
    hasTopBar: !!document.querySelector('.rumination-toolbar-wrap'),
    hasLock: !!document.querySelector('.rumination-workbench .absolute.inset-0'),
  }));
  console.log('guided layout:', JSON.stringify(layout));
  await page.screenshot({ path: '/home/gitclone/BeingDoing/output/verify-0922/12-guided-3col.png' });

  // 点「＋ 新建组合」→ 草稿态 → 中间对话锁屏
  await page.locator('.v4-combo-sidebar button:has-text("新建组合")').dispatchEvent('click');
  await page.waitForTimeout(800);
  const lock = await page.evaluate(() => ({
    hasLock: !!document.querySelector('.rumination-workbench .absolute.inset-0'),
    lockText: document.querySelector('.rumination-workbench .absolute.inset-0')?.innerText?.slice(0, 60),
  }));
  console.log('lock:', JSON.stringify(lock));
  await page.screenshot({ path: '/home/gitclone/BeingDoing/output/verify-0922/13-guided-locked.png' });

  await browser.close();
  console.log('DONE');
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
