/** 可读中文步骤对应的固定执行能力；只在本次隔离页面操作。 */
export async function testScenario(page, base, definition, check) {
  for (let index = 0; index < definition.steps.length; index++) {
    const step = definition.steps[index];
    if (step.action === 'navigate') {
      if (!step.value.startsWith('/') || step.value.startsWith('//')) throw new Error('仅允许本次测试页面');
      await page.goto(base + step.value, { waitUntil: 'networkidle' });
    } else if (step.action === 'click') {
      const button = page.getByRole('button', { name: step.value, exact: true });
      const target = button.or(page.getByRole('link', { name: step.value, exact: true }));
      await target.click();
    } else if (step.action === 'fill') {
      const label = page.getByLabel(step.label, { exact: true });
      await label.or(page.getByPlaceholder(step.label, { exact: true })).fill(step.value);
    } else if (step.action === 'message') {
      await page.locator('textarea.flow-input-field').fill(step.value);
    } else if (step.action === 'key' && ['Enter', 'Escape', 'Tab'].includes(step.value)) {
      await page.keyboard.press(step.value);
    } else { throw new Error(`未知操作：${step.action}`); }
    for (const criterion of definition.ui_checks.filter(item => item.step === index + 1)) {
      const { type, value } = criterion;
      if (type === 'url') {
        await page.waitForURL(url => url.origin === base && url.pathname === value);
        check(true, `第${index + 1}步跳转到${value}`);
      } else if (type === 'no_overflow') {
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `第${index + 1}步无横向溢出`);
      } else if (type === 'visible' || type === 'hidden') {
        const target = page.getByText(value, { exact: true });
        await target.waitFor({ state: type === 'visible' ? 'visible' : 'hidden', timeout: 10000 });
        check(true, `第${index + 1}步 ${type}：${value}`);
      } else if (type === 'disabled' || type === 'enabled') {
        const target = page.getByRole('button', { name: value, exact: true });
        await target.waitFor({ state: 'visible' });
        check(type === 'disabled' ? await target.isDisabled() : await target.isEnabled(), `第${index + 1}步按钮${type}：${value}`);
      } else if (type === 'input_value') {
        check(await page.locator('textarea.flow-input-field').inputValue() === value, `第${index + 1}步输入值保持`);
      } else { throw new Error(`未知断言：${type}`); }
    }
  }
}
