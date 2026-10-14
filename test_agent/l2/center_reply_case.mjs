import { targetReply, checkReply } from './reply_assertions.mjs';

export async function testReply(page, check) {
  await page.setContent('<p>期望答案</p><div class="flow-msg-ai-content">期望答案</div><div class="flow-msg-ai-content">新的回答</div><button class="flow-send-btn is-stop"></button>');
  let finished = false;
  const pending = targetReply(page, 1, 5000).then(reply => { finished = true; return reply; });
  await page.waitForTimeout(100);
  check(!finished, '流式期间不得提前判定');
  await page.locator('button').evaluate(el => el.classList.remove('is-stop'));
  const reply = await pending;
  check(checkReply(reply, { expected_hint: '期望答案' }).failures.length === 1, '用户和旧回复中的文字不能命中');
  check(checkReply(reply, { expected_keywords: ['新的回答'] }).failures.length === 0, '目标回复可以命中');
  let rejected = false;
  try { await targetReply(page, null, 5000); } catch { rejected = true; }
  check(rejected, '缺少目标轮次必须拒绝');
}
