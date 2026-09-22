/* rumination v4 加载卡死调试：抓 console / 页面 URL / DOM 状态 */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join('/home/gitclone/BeingDoing/test_agent/l2/node_modules', 'playwright'));

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', args: ['--no-sandbox'] });
  const token = fs.readFileSync('/tmp/.smoke_token', 'utf8').trim();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript((tk) => {
    localStorage.setItem('token', tk);
    localStorage.setItem('explore_user_survey_327018ad-2fd8-4da6-8d80-2cb409d03d93', '1');
    localStorage.setItem('explore_user_privacy_ack_327018ad-2fd8-4da6-8d80-2cb409d03d93', '1');
    localStorage.setItem('auth-storage', JSON.stringify({
      state: {
        user: { user_id: '327018ad-2fd8-4da6-8d80-2cb409d03d93', email: 'testzkx3@163.com', phone: null, username: 'cece', avatar_url: null, is_super_admin: false, email_verified: true },
        token: tk, isAuthenticated: true, recoveryMode: false,
      }, version: 0,
    }));
  }, token);
  const page = await context.newPage();
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('[console]', m.type(), m.text().slice(0, 300)); });
  page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 500)));
  page.on('response', (r) => { if (r.status() >= 400) console.log('[http]', r.status(), r.url().slice(0, 140)); });

  await page.goto('http://127.0.0.1:3000/explore/chat/rumination?code=WFLBEY74YN', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(6000);
  console.log('URL:', page.url());
  const dom = await page.evaluate(() => ({
    v4root: !!document.querySelector('.rumination-v4-root'),
    loading: document.body.innerText.includes('加载中'),
    bodyText: document.body.innerText.slice(0, 200),
  }));
  console.log('DOM:', JSON.stringify(dom));
  await page.screenshot({ path: '/home/gitclone/BeingDoing/output/verify-0922/08-rumination-debug.png' });
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
