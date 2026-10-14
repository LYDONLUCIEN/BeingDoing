import { prepareAccount, testAccount } from './center_account_case.mjs';
import { testDesktop } from './center_desktop_case.mjs';
import { testScenario } from './center_scenario.mjs';
import { prepareRumination, testRumination } from './center_rumination_case.mjs';
import { testReply } from './center_reply_case.mjs';
import { prepareChat, testChat } from './center_chat_case.mjs';
import { prepareAdmin, testAdmin } from './center_admin_case.mjs';
/** 固定浏览器用例。真实页面配受控 API；不会访问线上业务接口。 */
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { chromium, webkit } from 'playwright';

const [suite, artifacts, definitionPath] = process.argv.slice(2);
const definition = suite === 'scenario' ? JSON.parse(fs.readFileSync(definitionPath, 'utf8')) : null;
const fixtureSuite = definition?.fixture || suite;
const root = process.cwd();
const report = { passed: false, counts: { assertions: 0 }, error: null, views: [] };
function check(value, message) {
  report.counts.assertions += 1;
  if (!value) throw new Error(message);
}
const allocator = net.createServer();
await new Promise(resolve => allocator.listen(0, '127.0.0.1', resolve));
const port = allocator.address().port;
await new Promise(resolve => allocator.close(resolve));
const base = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, [path.join(root, 'src/frontend/node_modules/next/dist/bin/next'), 'dev', '-H', '127.0.0.1', '-p', String(port)], {
  cwd: path.join(root, 'src/frontend'), stdio: 'inherit',
  // API 只指向本次隔离前端的同源地址，由浏览器夹具统一拦截，绝不转发到已有业务服务。
  env: { ...process.env, NEXT_PUBLIC_API_URL: base, NEXT_TELEMETRY_DISABLED: '1' },
});
let browser;
try {
  let ready = false;
  for (let i = 0; i < 240; i++) {
    if (server.exitCode !== null) throw new Error('隔离前端未能启动');
    try { const response = await fetch(base); if (response.ok) { ready = true; break; } } catch {}
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!ready) throw new Error('隔离前端启动超时');
  for (const [engine, type] of [['chromium', chromium], ['webkit', webkit]]) {
    browser = await type.launch({ headless: true });
    const views = (suite === 'scenario' ? [390, 1440] : ['home', 'chat', 'rumination', 'account'].includes(suite) ? [360, 390, 430, 820, 1440] : [1440])
      .flatMap(width => (suite === 'chat' && [360, 1440].includes(width) ? ['values', 'strengths', 'interests', 'purpose'] : ['values']).map(phase => ({ width, phase })));
    for (const { width, phase } of views) {
      const viewName = `${engine}-${width}${suite === 'chat' ? `-${phase}` : ''}`;
      const context = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 768, hasTouch: width < 768, reducedMotion: 'reduce', serviceWorkers: 'block' });
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.pathname.startsWith('/api/')) {
          await route.fulfill({ json: { code: 200, message: '受控测试响应', data: {} } });
        } else if (url.origin === base || url.protocol === 'data:') {
          await route.continue();
        } else { await route.abort(); }
      });
      const adminState = suite === 'admin-center' ? await prepareAdmin(context) : null;
      await context.tracing.start({ screenshots: true, snapshots: true });
      let page = await context.newPage();
      const chatState = fixtureSuite === 'chat' ? await prepareChat(context, phase) : null;
      const ruminationState = ['rumination', 'desktop'].includes(fixtureSuite) ? await prepareRumination(context) : null;
      const accountState = fixtureSuite === 'account' ? await prepareAccount(context) : null;
      try {
        if (suite === 'scenario') {
          await testScenario(page, base, definition, check);
          report.views.push(`${engine}/${width}/scenario`);
          continue;
        }
        if (suite === 'desktop') {
          await testDesktop(page, base, ruminationState, check, path.join(artifacts, viewName));
          report.views.push(`${engine}/desktop-width-and-height`);
          continue;
        }
        if (suite === 'account') {
          await testAccount(page, base, accountState, check, async () => { await page.close(); page = await context.newPage(); return page; });
          report.views.push(`${engine}/${width}${suite === 'chat' ? `/${phase}` : ''}`);
          continue;
        }
        if (suite === 'rumination') {
          await testRumination(page, base, ruminationState, check, path.join(artifacts, viewName));
          report.views.push(`${engine}/${width}${suite === 'chat' ? `/${phase}` : ''}`);
          continue;
        }
        if (suite === 'reply-integrity') {
          await testReply(page, check);
          report.views.push(`${engine}/${width}${suite === 'chat' ? `/${phase}` : ''}`);
          continue;
        }
        if (suite === 'chat') {
          await testChat(page, base, chatState, check);
          report.views.push(`${engine}/${width}${suite === 'chat' ? `/${phase}` : ''}`);
          continue;
        }
        if (suite === 'admin-center') {
          await testAdmin(page, base, adminState, check);
          report.views.push(`${engine}/${width}${suite === 'chat' ? `/${phase}` : ''}`);
          continue;
        }
        if (suite !== 'home') throw new Error(`尚未实现套件: ${suite}`);
        await page.goto(base, { waitUntil: 'networkidle', timeout: 120000 });
        await page.locator('html[data-landing="true"]').waitFor();
        const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
        check(dimensions.scroll <= dimensions.width + 1, `${engine}/${width}: 页面横向溢出 ${dimensions.scroll}`);
        if (width >= 768) {
          const dot = await page.locator('.ol-review-dots button[aria-current="true"]').boundingBox();
          check(dot && Math.abs(dot.width - 23) < 0.5 && Math.abs(dot.height - 6) < 0.5, `${engine}/${width}: 桌面评价分页保持原有23×6尺寸`);
        }
        const hero = page.locator('.ol-hero-copy .ol-hero-cta');
        await hero.click({ trial: true });
        check(true, '主 CTA 可点击');
        const names = new Set();
        const dots = page.locator('.ol-review-dots button');
        for (let i = 0; i < await dots.count(); i++) {
          await dots.nth(i).click();
          for (const card of await page.locator('.ol-review-card').all()) {
            if (await card.isVisible()) names.add(await card.locator('.ol-review-author b').innerText());
          }
        }
        check(names.size === 9, `${engine}/${width}: 九条评价仅可访问 ${names.size} 条`);
        if (width < 768) {
          await page.evaluate(() => window.scrollTo(0, 0));
          const toggle = page.getByRole('button', { name: '打开导航菜单' });
          await toggle.click();
          check(await page.locator('#mobile-navigation').isVisible(), '手机菜单打开');
          await page.keyboard.press('Escape');
          check(await page.locator('#mobile-navigation').count() === 0, 'Escape 关闭菜单');
          await toggle.click();
          await page.locator('#mobile-navigation a[href="/about"]').click();
          await page.waitForURL('**/about');
          await page.locator('.ol-hero-copy').waitFor({ state: 'detached' });
          await page.waitForLoadState('networkidle');
          check(await page.locator('#mobile-navigation').count() === 0, '跳转后菜单关闭');
          // 导航验收结束后，在新页面进行首页其余操作，避免将 WebKit 的旧导航状态带入下一项。
          await page.close();
          page = await context.newPage();
          await page.goto(base, { waitUntil: 'networkidle' });
          const cards = page.locator('.ol-phase-cards');
          await cards.evaluate(el => { el.scrollLeft = el.scrollWidth; });
          check(await page.locator('.ol-phase-card').last().isVisible(), '最后一张旅程卡可访问');
        }
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(artifacts, `${engine}-${width}-viewport.png`) });
        await page.screenshot({ path: path.join(artifacts, `${engine}-${width}.png`), fullPage: true });
        await page.locator('.ol-hero-copy .ol-hero-cta').click();
        await page.locator('input[type="password"]').waitFor({ state: 'visible' });
        check(true, '未登录探索需要登录');
        report.views.push(`${engine}/${width}${suite === 'chat' ? `/${phase}` : ''}`);
      } finally {
        await page.screenshot({ path: path.join(artifacts, `${viewName}-last.png`), fullPage: true }).catch(() => {});
        await context.tracing.stop({ path: path.join(artifacts, `${viewName}-trace.zip`) });
        await context.close();
      }
    }
    await browser.close(); browser = null;
  }
  report.passed = true;
} catch (error) {
  report.error = error instanceof Error ? error.stack : String(error);
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
  fs.writeFileSync(path.join(artifacts, 'results.json'), JSON.stringify(report, null, 2));
}
console.log(JSON.stringify(report));
process.exit(report.passed ? 0 : 1);
