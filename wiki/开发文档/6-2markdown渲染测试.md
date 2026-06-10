# Markdown 渲染预处理测试

## 背景

AI 输出的 Markdown 内容中，`**加粗**` 和 `*斜体*` 标记紧邻中文标点（如 `，。！？`）时，可能导致前端渲染失败，星号原样显示。

修复方案：在前端 `MessageContent.tsx` 中，传给 Markdown 渲染组件前进行轻量正则预处理，在中文标点与 `**`/`*` 之间插入空格。

## 修改的文件

- `src/frontend/components/explore/MessageContent.tsx` — 新增 `preprocessMarkdown` 函数

## 测试文件

`test/test_preprocess_markdown.py`

### 运行方式

```bash
conda run -n py312 python -m pytest test/test_preprocess_markdown.py -v
```

### 测试覆盖（55 个用例）

| 类别 | 数量 | 说明 |
|------|------|------|
| `**` 加粗 + 中文标点 | 17 | 逗号、句号、问号、感叹号、分号、冒号、全角括号、方括号、引号、顿号 |
| `*` 斜体 + 中文标点 | 7 | 逗号、句号、问号、括号、`**` 与 `*` 区分 |
| 不误伤正常 Markdown | 14 | 汉字紧邻、英文内容、标题、列表、行内代码、空文本、多行 |
| 英文标点不处理 | 4 | 逗号、句号、问号、括号 |
| 混合场景 | 8 | 加粗+斜体混合、多行、真实 AI 输出、嵌套标记、连续标点 |
| 边界场景 | 5 | 行首/行末、未闭合标记、单星号、三星号 |

### 注意事项

- 测试用 Python 编写（与前端 TypeScript 逻辑等价），使用项目现有的 pytest 环境
- 函数逻辑为纯字符串正则替换，不依赖 React/浏览器环境，Python 验证即可
- 如果前端函数逻辑有改动，需同步更新测试文件中的 `preprocessMarkdown` 函数
