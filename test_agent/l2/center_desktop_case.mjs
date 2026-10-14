/** 普通电脑保持横向工作台；低高度与窄宽度分别验收。 */
export async function testDesktop(page, base, fixture, check, evidence) {
  await page.goto(`${base}/explore/chat/rumination?code=FIXTURE`, { waitUntil: 'networkidle' });
  const input = page.locator('textarea.flow-input-field');
  await input.waitFor();
  await page.getByRole('button', { name: '帮助他人', exact: true }).click();
  await page.getByRole('button', { name: '倾听', exact: true }).click();
  await page.getByRole('button', { name: /开始探索/ }).click();
  await input.fill('布局改变也应保留的草稿');
  for (const width of [1440, 1280, 1024, 820]) {
    for (const height of [900, 700, 600]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(150);
      if (width >= 1024) {
        const expand = page.getByRole('button', { name: '展开组合选择器', exact: true });
        if (await expand.isVisible()) await expand.click();
      }
      const box = await input.boundingBox();
      const textSize = await input.evaluate(el => parseFloat(getComputedStyle(el).fontSize));
      check(box && box.width >= textSize * 12 && box.y >= 0 && box.y + box.height <= height + 1, `${width}x${height} 输入框应完整可见并容纳至少十二个汉字`);
      check(await input.inputValue() === '布局改变也应保留的草稿', '尺寸改变不清空输入');
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), '桌面页面不横向溢出');
      if (width >= 1024) {
        check(await page.locator('.v4-combo-sidebar').isVisible(), '普通桌面高度不足也保留组合侧栏');
        check(await page.locator('.combo-toolbar').count() === 0, '高度变化不把 guided 改为 classic');
      } else {
        const open = page.getByRole('button', { name: '打开组合选择器', exact: true });
        await open.click();
        check(await page.getByRole('dialog', { name: '组合选择器', exact: true }).isVisible(), '窄桌面可主动打开覆盖式选择器');
        await page.screenshot({ path: `${evidence}-${width}x${height}-selector.png` });
        await page.keyboard.press('Escape');
        check(await input.inputValue() === '布局改变也应保留的草稿', '关闭选择器不清空输入');
      }
      await page.screenshot({ path: `${evidence}-${width}x${height}.png` });
    }
  }
}
