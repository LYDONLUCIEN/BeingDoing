import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { testReply } from './center_reply_case.mjs';

test('用户输入和历史回复不构成目标回复命中，流式期间等待完成', async () => {
  const browser = await chromium.launch();
  try { await testReply(await browser.newPage(), (value, message) => assert.ok(value, message)); }
  finally { await browser.close(); }
});
