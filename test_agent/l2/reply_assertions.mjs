/** 对话断言只读取本次发送后产生的目标回复，不能匹配用户输入和历史。 */
export async function targetReply(page, startIndex, timeout) {
  if (startIndex === null) throw new Error('没有本次发送的目标轮次');
  await page.locator('.flow-msg-ai-content').nth(startIndex).waitFor({ state: 'visible', timeout });
  await page.waitForFunction(() => !document.querySelector('.flow-send-btn.is-stop'), null, { timeout });
  const reply = (await page.locator('.flow-msg-ai-content').nth(startIndex).innerText()).trim();
  if (!reply) throw new Error('目标 AI 回复为空');
  return reply;
}

export function checkReply(text, assertions) {
  const failures = [];
  const required = [assertions.expected_hint, ...(assertions.expected_keywords || [])].filter(x => typeof x === 'string' && x.trim());
  const forbidden = (assertions.no_leak_tags || []).filter(x => typeof x === 'string' && x.trim());
  for (const expected of required) if (!text.includes(expected.trim())) failures.push(`目标回复未包含: ${expected}`);
  for (const tag of forbidden) if (text.includes(tag.trim())) failures.push(`目标回复泄露: ${tag}`);
  return { failures, count: required.length + forbidden.length };
}
