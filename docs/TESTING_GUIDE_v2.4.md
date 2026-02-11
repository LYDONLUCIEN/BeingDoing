# v2.4 启动和测试指南

## 快速启动

### 1. 启动后端
```bash
cd /home/gitclone/BeingDoing/src/backend
uvicorn app.main:app --reload --port 8000
```

### 2. 启动前端
```bash
cd /home/gitclone/BeingDoing/src/frontend
npm run dev
# 访问 http://localhost:3000
```

## 测试流程

### 完整测试步骤

1. **登录/注册**
   - 访问 http://localhost:3000/auth/login
   - 登录或注册账号

2. **创建新session**
   - 访问 http://localhost:3000/explore
   - 点击"新的开始"

3. **查看步骤理论介绍**
   - 应该看到"探索重要的事（价值观）"页面
   - 包含理论基础说明
   - 点击"开始探索"按钮

4. **第一道题的引导**
   - AI应该展示题目引导语
   - 包含题目内容
   - 输入框可用

5. **回答题目**
   - 输入回答（尽量具体，包含例子）
   - AI会继续提问挖掘
   - 2-5轮对话后，AI判断充分

6. **Answer Card确认**
   - 回答充分后，弹出EnhancedAnswerCard
   - 显示：题目 + 你的回答
   - 两个按钮："确认并继续" / "继续讨论"
   - 可以点击编辑图标修改答案

7. **移动到下一题**
   - 点击"确认并继续"
   - 当前题目折叠
   - 出现下一道题的引导

8. **查看已完成题目**
   - 点击折叠的题目可以展开
   - 查看之前的对话历史

## 验证要点

### 后端验证
- [ ] reasoning_v2节点正常工作
- [ ] question_progress正确返回
- [ ] answer_card在充分时生成
- [ ] 步骤介绍只显示一次

### 前端验证
- [ ] 步骤理论介绍动画流畅
- [ ] 题目卡片折叠/展开正常
- [ ] Answer Card 3D效果正常
- [ ] 滚动条自定义样式生效
- [ ] 响应式布局正常

### 功能验证
- [ ] 逐题呈现（不会跳步骤）
- [ ] 充分性判断合理（2-5轮）
- [ ] 编辑答案功能正常
- [ ] 对话历史保存完整

## 常见问题

### 问题1：前端编译错误
```bash
# 清理缓存重新安装
rm -rf .next node_modules
npm install
npm run dev
```

### 问题2：后端import错误
```bash
# 检查依赖
pip install -r requirements.txt

# 检查文件路径
ls -la app/domain/step_guidance.py
ls -la app/core/agent/question_flow.py
```

### 问题3：题目不显示
- 检查数据库中是否有题目数据
- 检查category映射是否正确
- 查看后端日志

### 问题4：answer_card不弹出
- 检查对话轮数（需要2轮以上）
- 检查回答长度（需要30字以上）
- 查看后端reasoning日志

## 调试技巧

### 后端调试
```python
# 在reasoning_v2.py中添加日志
_append_log(state, f"当前场景：{scene}", meta={...})
```

### 前端调试
```typescript
// 在page.tsx中添加console
console.log('Question Progress:', questionProgress);
console.log('Answer Card:', answerCard);
```

### 查看完整日志
- 前端：浏览器控制台（F12）
- 后端：terminal输出
- Agent日志：点击"调试"按钮（超级管理员）

## 性能检查

### 动画性能
- 打开浏览器Performance面板
- 录制交互过程
- 查看FPS是否稳定在60

### 内存使用
- 长时间使用后检查内存
- 多次折叠/展开检查是否泄漏

## 回滚方案

如果遇到严重问题，可以回滚：

```bash
# 后端回滚
cd /home/gitclone/BeingDoing/src/backend
git checkout app/core/agent/graph.py
git checkout app/api/v1/chat.py

# 前端回滚
cd /home/gitclone/BeingDoing/src/frontend
cp app/\(main\)/explore/flow/page.tsx.backup app/\(main\)/explore/flow/page.tsx
```

## 下一步

测试完成后：
1. 记录发现的bug到issue
2. 优化体验细节
3. 准备上线部署

---

**文档版本**: v2.4
**创建时间**: 2026-02-11
