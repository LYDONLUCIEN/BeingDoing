#!/bin/bash
# orchestrator.sh v2 - 智能调度版

TODO_FILE="${1:-todo.md}"    # 支持传参指定文件
LOG_DIR="/home/gitclone/BeingDoing/wiki/claude开发/agent-logs"
TASKS_FILE="/home/gitclone/BeingDoing/wiki/claude开发/tasks.json"
PROJECT_DIR="/home/gitclone/BeingDoing"

mkdir -p "$LOG_DIR"

echo "========================================="
echo "  Claude Code 智能调度器 v2"
echo "  时间: $(date)"
echo "  待办文件: ${TODO_FILE}"
echo "========================================="

# ============================================
# 阶段一：主智能体分析 todo，生成结构化任务列表
# ============================================
echo ""
echo "[$(date '+%H:%M:%S')] 📋 阶段一：主智能体分析任务文件..."

claude --print \
    "你是一个项目经理智能体。请阅读以下文件并拆解任务。

请读取当前目录下的文件：${TODO_FILE}

要求：
1. 理解文件中所有待办任务（无论它用什么格式写的）
2. 将每个任务拆解为独立的、可执行的开发子任务
3. 按依赖关系排序（被依赖的任务排前面）
4. 输出一个 JSON 文件到 ${TASKS_FILE}，格式严格如下：

{
  \"tasks\": [
    {
      \"id\": 1,
      \"title\": \"简短任务标题\",
      \"description\": \"详细的开发指令，包含技术要求、涉及的文件路径、验收标准\",
      \"original_text\": \"对应原始 todo 中的那段文字\"
    }
  ]
}

注意：
- description 要足够详细，让一个独立的开发者 agent 拿到就能直接干活
- original_text 保留原文，后续用于标记完成状态
- 只输出 JSON 文件，不要输出其他内容" \
    > "${LOG_DIR}/phase1-planning.log" 2>&1

# 检查任务文件是否生成成功
if [ ! -f "$TASKS_FILE" ]; then
    echo "❌ 主智能体未能生成任务文件，请检查日志: ${LOG_DIR}/phase1-planning.log"
    exit 1
fi

TOTAL_TASKS=$(python3 -c "import json; print(len(json.load(open('${TASKS_FILE}'))['tasks']))" 2>/dev/null)

if [ -z "$TOTAL_TASKS" ] || [ "$TOTAL_TASKS" -eq 0 ]; then
    echo "❌ 任务列表为空或格式错误，请检查 ${TASKS_FILE}"
    exit 1
fi

echo "[$(date '+%H:%M:%S')] ✅ 主智能体拆分出 ${TOTAL_TASKS} 个子任务"
echo ""

# ============================================
# 阶段二：逐个派发 sub-agent 执行任务
# ============================================
echo "[$(date '+%H:%M:%S')] 🚀 阶段二：开始逐个执行子任务..."
echo ""

COMPLETED=0
FAILED=0

for i in $(seq 0 $((TOTAL_TASKS - 1))); do
    # 从 JSON 中提取任务信息
    TASK_ID=$(python3 -c "import json; t=json.load(open('${TASKS_FILE}'))['tasks'][$i]; print(t['id'])")
    TASK_TITLE=$(python3 -c "import json; t=json.load(open('${TASKS_FILE}'))['tasks'][$i]; print(t['title'])")
    TASK_DESC=$(python3 -c "import json; t=json.load(open('${TASKS_FILE}'))['tasks'][$i]; print(t['description'])")
    
    LOG_FILE="${LOG_DIR}/task-${TASK_ID}.log"
    
    echo "────────────────────────────────────────"
    echo "[$(date '+%H:%M:%S')] 📌 任务 ${TASK_ID}/${TOTAL_TASKS}: ${TASK_TITLE}"
    echo "────────────────────────────────────────"
    
    # 派发给 sub-agent
    claude --print \
        --dangerously-skip-permissions \
        "你是一个专业开发者 agent。请完成以下开发任务：

任务标题：${TASK_TITLE}

详细要求：
${TASK_DESC}

项目根目录：${PROJECT_DIR}

规则：
1. 直接在项目中创建或修改文件
2. 写高质量、有注释的代码
3. 如果涉及新增依赖，更新 package.json 或 requirements.txt 等
4. 完成后简要总结你创建/修改了哪些文件" \
        2>&1 | tee "$LOG_FILE"
    
    EXIT_CODE=${PIPESTATUS[0]}
    
    if [ $EXIT_CODE -eq 0 ]; then
        COMPLETED=$((COMPLETED + 1))
        echo ""
        echo "[$(date '+%H:%M:%S')] ✅ 任务 ${TASK_ID} 完成 (${COMPLETED}/${TOTAL_TASKS})"
        
        # 实时更新 tasks.json 中的状态
        python3 -c "
import json
with open('${TASKS_FILE}', 'r') as f:
    data = json.load(f)
data['tasks'][$i]['status'] = 'done'
with open('${TASKS_FILE}', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"
    else
        FAILED=$((FAILED + 1))
        echo ""
        echo "[$(date '+%H:%M:%S')] ❌ 任务 ${TASK_ID} 失败，日志: ${LOG_FILE}"
        
        python3 -c "
import json
with open('${TASKS_FILE}', 'r') as f:
    data = json.load(f)
data['tasks'][$i]['status'] = 'failed'
with open('${TASKS_FILE}', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"
    fi
    
    echo ""
    sleep 5  # API 冷却
done

# ============================================
# 阶段三：主智能体回写原始 todo 文件
# ============================================
echo "[$(date '+%H:%M:%S')] 📝 阶段三：更新原始待办文件..."

claude --print \
    --dangerously-skip-permissions \
    "请读取 ${TASKS_FILE}，查看每个任务的 status 字段。
然后修改 ${TODO_FILE}，将已完成的任务（status 为 done）标记为完成。

标记方式：保持原文件的格式风格，在对应任务前加上 ✅ 或改为完成状态。
如果原文是 - [ ] 格式就改为 - [x]，
如果原文是数字编号就在后面加 （已完成），
总之用符合原文风格的方式标记。

对于 status 为 failed 的任务，标记为 ❌ 待修复。" \
    > "${LOG_DIR}/phase3-mark-done.log" 2>&1

# ============================================
# 最终汇总
# ============================================
echo ""
echo "========================================="
echo "  🎉 全部任务处理完毕"
echo "  时间: $(date)"
echo "  完成: ${COMPLETED}  失败: ${FAILED}  总计: ${TOTAL_TASKS}"
echo "========================================="
echo ""
echo "📋 最终待办状态："
cat "$TODO_FILE"