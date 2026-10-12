import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import MessageContent from '../components/explore/MessageContent';
import V4ComboMatrixSelector from '../components/explore/ruminationV4/V4ComboMatrixSelector';

test('模型 Markdown 不得创建脚本、iframe、事件处理器或危险 URL', () => {
  const html = renderToStaticMarkup(<MessageContent content={'<iframe src="https://evil.example"></iframe>\n<script>alert(1)</script>\n<a href="javascript:alert(1)">link</a>\n<img src=x onerror="alert(1)">'} />);
  assert.doesNotMatch(html, /<iframe|<script|javascript:|onerror=/i);
});

test('安全处理保留正常 Markdown 表格、强调和链接', () => {
  const html = renderToStaticMarkup(<MessageContent content={'| 名称 | 内容 |\n| --- | --- |\n| A | **优势** |\n\n[链接](https://example.com)'} />);
  assert.match(html, /<table>/);
  assert.match(html, /<strong>优势<\/strong>/);
  assert.match(html, /href="https:\/\/example.com"/);
});

test('组合选择器将优势名称作为文字显示', () => {
  const html = renderToStaticMarkup(<V4ComboMatrixSelector passions={['热爱']} strengths={['<img src=x onerror="alert(1)">\n第二行']} onCreateCombo={() => {}} />);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
  assert.match(html, /第二行/);
});
