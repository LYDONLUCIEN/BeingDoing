/* v4 外观面板遮挡诊断 */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join('/home/gitclone/BeingDoing/test_agent/l2/node_modules', 'playwright'));

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', args: ['--no-sandbox'] });
  const token = fs.readFileSync('/tmp/.smoke_token2', 'utf8').trim();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript((tk) => {
    localStorage.setItem('token', tk);
    localStorage.setItem('explore_user_survey_eddc095a-8357-4f4b-bfa9-e4d46f7f856b', '1');
    localStorage.setItem('explore_user_privacy_ack_eddc095a-8357-4f4b-bfa9-e4d46f7f856b', '1');
    localStorage.setItem('auth-storage', JSON.stringify({
      state: { user: { user_id: 'eddc095a-8357-4f4b-bfa9-e4d46f7f856b', email: 'v4user@example.com', phone: null, username: 'v4user', avatar_url: null, is_super_admin: false, email_verified: true }, token: tk, isAuthenticated: true, recoveryMode: false }, version: 0,
    }));
  }, token);
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:3000/explore/chat/rumination?code=WELZ65ERHS', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);
  // dismiss intro modal
  const okBtn = await page.$('div.fixed.inset-0 button:text-is("确定")');
  if (okBtn) await okBtn.click();
  await page.waitForTimeout(500);

  await page.locator('button[aria-label="页面设置"]').dispatchEvent('click');
  await page.waitForTimeout(600);

  const info = await page.evaluate(() => {
    const panel = document.querySelector('.ol-chat-appearance-panel');
    if (!panel) return { open: false };
    const opt = panel.querySelector('.ol-chat-appearance-option');
    const r = opt.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const cover = document.elementFromPoint(cx, cy);
    // 沿遮挡元素向上找带 z-index/position 的祖先链
    const chainOf = (el) => {
      const out = [];
      let cur = el;
      while (cur && cur !== document.body) {
        const cs = getComputedStyle(cur);
        if (cs.position !== 'static' || cs.zIndex !== 'auto' || cs.backdropFilter !== 'none' || cs.transform !== 'none') {
          out.push(`${cur.className?.toString().slice(0, 60) || cur.tagName} pos=${cs.position} z=${cs.zIndex} bf=${cs.backdropFilter !== 'none'}`);
        }
        cur = cur.parentElement;
      }
      return out;
    };
    const panelChain = chainOf(panel);
    return {
      open: true,
      panelRect: panel.getBoundingClientRect().toJSON(),
      optCenter: { cx, cy },
      coverClass: cover ? cover.className?.toString().slice(0, 80) : null,
      coverChain: cover ? chainOf(cover) : [],
      panelChain,
    };
  });
  console.log(JSON.stringify(info, null, 1));
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
