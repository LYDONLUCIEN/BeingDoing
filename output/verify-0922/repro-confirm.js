/* 复现：rumination v4 结论卡「确认」无法点击 */
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
  }, { tk: token, u: uid });
  const page = await context.newPage();
  await page.route('**/api/v1/simple-chat/rumination-v4/state*', async (route) => {
    const resp = await route.fetch();
    const json = await resp.json();
    if (json?.data?.state) {
      json.data.state.final_selection = { ...(json.data.state.final_selection || {}), submitted: false };
      json.data.state.intro_shown = true;
    }
    await route.fulfill({ response: resp, json });
  });

  page.on('console', (m) => { if (m.type() === 'error') console.log('[console.error]', m.text().slice(0, 300)); });
  page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 500)));

  await page.goto('http://127.0.0.1:3000/explore/chat/rumination?code=XV1F9OFYQ1', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3500);

  // 结论卡状态勘察
  const card = await page.evaluate(() => {
    const el = document.querySelector('.conclusion-card-v4');
    if (!el) return { found: false };
    const ta = el.querySelector('textarea');
    const btns = Array.from(el.querySelectorAll('button')).map((b) => ({
      text: b.innerText.trim(), disabled: b.disabled,
    }));
    const r = el.getBoundingClientRect();
    const cover = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height - 10, 60));
    return {
      found: true,
      textarea: ta ? { disabled: ta.disabled, value: ta.value.slice(0, 30) } : null,
      buttons: btns,
      coveredBy: cover && !el.contains(cover) ? cover.className?.toString().slice(0, 80) : null,
    };
  });
  console.log('card:', JSON.stringify(card, null, 1));

  // 填写并确认，监听确认请求
  if (card.found && card.textarea && !card.textarea.disabled) {
    const respPromise = page.waitForResponse((r) => r.url().includes('rumination-v4'), { timeout: 20000 }).catch(() => null);
    await page.fill('.conclusion-card-v4 textarea', '用视觉叙事帮助青少年完成自我表达与情绪梳理');
    await page.waitForTimeout(300);
    const beforeClick = await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('.conclusion-card-v4 button')).find((x) => x.innerText.trim() === '确认');
      return b ? { disabled: b.disabled } : null;
    });
    console.log('confirm button before click:', JSON.stringify(beforeClick));
    await page.locator('.conclusion-card-v4 button:has-text("确认")').first().dispatchEvent('click');
    const resp = await respPromise;
    if (resp) console.log('confirm resp:', resp.status(), resp.url().slice(-60), (await resp.text()).slice(0, 200));
    else console.log('confirm resp: NONE (请求未发出)');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: '/home/gitclone/BeingDoing/output/verify-0922/14-confirm-test.png' });
  }
  await browser.close();
  console.log('DONE');
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
