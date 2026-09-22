/* Chat 页外观配置 + 工具栏常显 + rumination v4 冒烟验证 v2（双身份双 context） */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join('/home/gitclone/BeingDoing/test_agent/l2/node_modules', 'playwright'));

const BASE = 'http://127.0.0.1:3000';
const OUT = '/home/gitclone/BeingDoing/output/verify-0922';

const USER1 = { id: '327018ad-2fd8-4da6-8d80-2cb409d03d93', email: 'testzkx3@163.com', name: 'cece' };
const USER2 = { id: 'eddc095a-8357-4f4b-bfa9-e4d46f7f856b', email: 'v4user@example.com', name: 'v4user' };

async function makeContext(browser, tokenFile, user) {
  const token = fs.readFileSync(tokenFile, 'utf8').trim();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(({ tk, u }) => {
    localStorage.setItem('token', tk);
    localStorage.setItem(`explore_user_survey_${u.id}`, '1');
    localStorage.setItem(`explore_user_privacy_ack_${u.id}`, '1');
    localStorage.setItem('auth-storage', JSON.stringify({
      state: {
        user: { user_id: u.id, email: u.email, phone: null, username: u.name, avatar_url: null, is_super_admin: false, email_verified: true },
        token: tk, isAuthenticated: true, recoveryMode: false,
      }, version: 0,
    }));
  }, { tk: token, u: user });
  return context;
}

async function dismissModals(page) {
  for (let i = 0; i < 4; i++) {
    const overlay = await page.$('div.fixed.inset-0');
    if (!overlay) return;
    let clicked = false;
    for (const label of ['确定', '开始探索', '开始', '我知道了', '知道了', '确认', '继续', '跳过']) {
      const btn = await page.$(`div.fixed.inset-0 button:text-is("${label}")`);
      if (btn) { await btn.click().catch(() => {}); clicked = true; break; }
    }
    if (!clicked) await page.keyboard.press('Escape');
    await page.waitForTimeout(600);
  }
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', args: ['--no-sandbox'] });

  // ── Part 1: 四阶段 chat 页（USER1 + WFLBEY74YN） ──
  const ctx1 = await makeContext(browser, '/tmp/.smoke_token', USER1);
  const page = await ctx1.newPage();
  const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` });

  await page.goto(`${BASE}/explore/chat/values?code=WFLBEY74YN`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2500);
  await dismissModals(page);
  await shot('01-values-default');

  const toolbarInfo = await page.evaluate(() => {
    const opacityOf = (sel) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el).opacity : 'missing';
    };
    const ai = document.querySelector('.flow-msg-ai-toolbar');
    return { ai: opacityOf('.flow-msg-ai-toolbar'), user: opacityOf('.flow-msg-user-toolbar'), aiButtons: ai ? ai.querySelectorAll('button').length : 0 };
  });
  console.log('toolbar:', JSON.stringify(toolbarInfo));

  await page.click('button[aria-label="页面设置"]');
  await page.waitForTimeout(500);
  await shot('02-appearance-panel');

  const clickOpt = async (label, nth = 0) => {
    const btns = await page.$$(`.ol-chat-appearance-panel button:text-is("${label}")`);
    if (btns[nth]) await btns[nth].click();
    await page.waitForTimeout(350);
  };
  await clickOpt('浅主题', 0);       // AI 气泡 → soft
  await clickOpt('主题实色', 1);     // 我的气泡 → theme（第二个「主题实色」）
  await clickOpt('纯白');
  await shot('03-values-custom');

  const persisted = await page.evaluate(() => {
    const p = JSON.parse(localStorage.getItem('openlife-chat-appearance') || '{}');
    return p.state && { aiBubble: p.state.aiBubble, userBubble: p.state.userBubble, background: p.state.background };
  });
  console.log('persisted:', JSON.stringify(persisted));

  await page.click('.ol-chat-appearance-panel footer button'); // 恢复推荐组合
  await page.waitForTimeout(400);
  await shot('04-values-reset');
  await ctx1.close();

  // ── Part 2: rumination v4（USER2 + WELZ65ERHS） ──
  const ctx2 = await makeContext(browser, '/tmp/.smoke_token2', USER2);
  const page2 = await ctx2.newPage();
  const shot2 = (name) => page2.screenshot({ path: `${OUT}/${name}.png` });

  await page2.goto(`${BASE}/explore/chat/rumination?code=WELZ65ERHS`, { waitUntil: 'networkidle', timeout: 45000 });
  await page2.waitForTimeout(3500);
  await dismissModals(page2);
  await shot2('05-rumination-v4-classic');

  const v4check = await page2.evaluate(() => ({
    isV4: !!document.querySelector('.rumination-v4-root'),
    layout: document.querySelector('.rumination-v4-root')?.getAttribute('data-rumination-layout'),
    skin: document.querySelector('.rumination-v4-root')?.getAttribute('data-rumination-skin'),
  }));
  console.log('v4:', JSON.stringify(v4check));

  await page2.locator('button[aria-label="页面设置"]').dispatchEvent('click');
  await page2.waitForTimeout(500);
  const clickOpt2 = async (label) => {
    await page2.locator(`.ol-chat-appearance-panel button:text-is("${label}")`).first().dispatchEvent('click');
    await page2.waitForTimeout(400);
  };
  await clickOpt2('组合解锁');
  await shot2('06-rumination-guided');
  await clickOpt2('横向工作台');
  await clickOpt2('静谧双页');
  await shot2('07-rumination-studio-folio');
  await clickOpt2('统一紫');
  await clickOpt2('实心高亮');
  await shot2('08-rumination-matrix-violet-solid');

  await browser.close();
  console.log('DONE');
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
