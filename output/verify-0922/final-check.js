/* 最终验证：用户工具栏常显 + violet×solid 矩阵配色 */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join('/home/gitclone/BeingDoing/test_agent/l2/node_modules', 'playwright'));

const BASE = 'http://127.0.0.1:3000';
const OUT = '/home/gitclone/BeingDoing/output/verify-0922';

async function makeContext(browser, tokenFile, user) {
  const token = fs.readFileSync(tokenFile, 'utf8').trim();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(({ tk, u }) => {
    localStorage.setItem('token', tk);
    localStorage.setItem(`explore_user_survey_${u.id}`, '1');
    localStorage.setItem(`explore_user_privacy_ack_${u.id}`, '1');
    localStorage.setItem('auth-storage', JSON.stringify({
      state: { user: { user_id: u.id, email: u.email, phone: null, username: u.name, avatar_url: null, is_super_admin: false, email_verified: true }, token: tk, isAuthenticated: true, recoveryMode: false }, version: 0,
    }));
  }, { tk: token, u: user });
  return context;
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', args: ['--no-sandbox'] });

  // 1. 用户工具栏常显
  const ctx1 = await makeContext(browser, '/tmp/.smoke_token', { id: '327018ad-2fd8-4da6-8d80-2cb409d03d93', email: 'testzkx3@163.com', name: 'cece' });
  const page = await ctx1.newPage();
  await page.goto(`${BASE}/explore/chat/values?code=WFLBEY74YN`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2500);
  const tb = await page.evaluate(() => {
    const o = (sel) => { const el = document.querySelector(sel); return el ? getComputedStyle(el).opacity : 'missing'; };
    return { ai: o('.flow-msg-ai-toolbar'), user: o('.flow-msg-user-toolbar') };
  });
  console.log('toolbar opacity:', JSON.stringify(tb));
  await page.screenshot({ path: `${OUT}/10-toolbar-final.png` });
  await ctx1.close();

  // 2. violet × solid 矩阵
  const ctx2 = await makeContext(browser, '/tmp/.smoke_token2', { id: 'eddc095a-8357-4f4b-bfa9-e4d46f7f856b', email: 'v4user@example.com', name: 'v4user' });
  const page2 = await ctx2.newPage();
  await page2.goto(`${BASE}/explore/chat/rumination?code=WELZ65ERHS`, { waitUntil: 'networkidle', timeout: 45000 });
  await page2.waitForTimeout(3500);
  const okBtn = await page2.$('div.fixed.inset-0 button:text-is("确定")');
  if (okBtn) await okBtn.click();
  await page2.waitForTimeout(500);
  await page2.locator('button[aria-label="页面设置"]').dispatchEvent('click');
  await page2.waitForTimeout(500);
  await page2.locator('.ol-chat-appearance-panel button:text-is("统一紫")').dispatchEvent('click');
  await page2.waitForTimeout(300);
  await page2.locator('.ol-chat-appearance-panel button:text-is("实心高亮")').dispatchEvent('click');
  await page2.waitForTimeout(500);
  const colors = await page2.evaluate(() => {
    const love = document.querySelector('.choice-card.love-card.selected');
    const strength = document.querySelector('.choice-card.strength-card.selected');
    return {
      loveBg: love ? getComputedStyle(love).backgroundImage.slice(0, 90) : 'missing',
      strengthBg: strength ? getComputedStyle(strength).backgroundColor : 'missing',
    };
  });
  console.log('matrix violet+solid:', JSON.stringify(colors));
  await page2.screenshot({ path: `${OUT}/11-matrix-violet-solid-fixed.png` });
  await browser.close();
  console.log('DONE');
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
