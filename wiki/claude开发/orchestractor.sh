#!/bin/bash
# orchestrator.sh - Claude Code 多任务自动调度器

TODO_FILE="todo.md"
LOG_DIR="./agent-logs"
PROJECT_DIR="/home/gitclone/BeingDoing"
MAX_PARALLEL=2  # 最大并行 sub-agent 数量，根据 API 限额调整

mkdir -p "$LOG_DIR"

# 读取所有未完成的任务
get_pending_tasks() {
    grep -n '^\- \[ \]' "$TODO_FILE"
}

# 标记任务完成
mark_done() {
    local line_num=$1
    sed -i "${line_num}s/- \[ \]/- [x]/" "$TODO_FILE"
    echo "[$(date '+%H:%M:%S')] ✅ 任务第${line_num}行已标记完成"
}

# 执行单个 sub-agent 任务
run_agent() {
    local line_num=$1
    local task_desc=$2
    local log_file="${LOG_DIR}/task-line${line_num}.log"
    
    echo "[$(date '+%H:%M:%S')] 🚀 启动 sub-agent: ${task_desc}"
    
    # 核心：使用 claude --print 非交互模式
    claude --print \
        --dangerously-skip-permissions \
        "你是一个专业开发者。请完成以下任务：
        
任务描述：${task_desc}

要求：
1. 在项目目录中直接修改/创建相关文件
2. 确保代码质量，加上必要的注释
3. 完成后简要总结你做了什么" \
        2>&1 | tee "$log_file"
    
    local exit_code=${PIPESTATUS[0]}
    
    if [ $exit_code -eq 0 ]; then
        mark_done "$line_num"
        echo "[$(date '+%H:%M:%S')] ✅ 任务完成: ${task_desc}"
    else
        echo "[$(date '+%H:%M:%S')] ❌ 任务失败: ${task_desc} (退出码: $exit_code)"
        echo "FAILED" >> "$log_file"
    fi
    
    return $exit_code
}

# ==================== 主循环 ====================
echo "========================================="
echo "  Claude Code 多任务调度器启动"
echo "  时间: $(date)"
echo "  项目: ${PROJECT_DIR}"
echo "========================================="

# 方案A：顺序执行（更稳定，推荐）
run_sequential() {
    while IFS= read -r line; do
        line_num=$(echo "$line" | cut -d: -f1)
        task_desc=$(echo "$line" | sed 's/^[0-9]*:- \[ \] //')
        
        run_agent "$line_num" "$task_desc"
        
        echo ""
        echo "--- 剩余未完成任务 ---"
        get_pending_tasks
        echo "----------------------"
        echo ""
        
        # 任务间冷却，避免 API 限流
        sleep 5
    done <<< "$(get_pending_tasks)"
}

# 方案B：并行执行（更快，但注意 API 限额）
run_parallel() {
    local pids=()
    local count=0
    
    while IFS= read -r line; do
        line_num=$(echo "$line" | cut -d: -f1)
        task_desc=$(echo "$line" | sed 's/^[0-9]*:- \[ \] //')
        
        # 后台启动 sub-agent
        run_agent "$line_num" "$task_desc" &
        pids+=($!)
        count=$((count + 1))
        
        # 达到并行上限时等待
        if [ $count -ge $MAX_PARALLEL ]; then
            wait -n  # 等待任一子进程完成
            count=$((count - 1))
        fi
        
        sleep 2
    done <<< "$(get_pending_tasks)"
    
    # 等待所有剩余任务
    wait "${pids[@]}"
}

# 选择执行模式
run_sequential
# run_parallel  # 取消注释切换为并行模式

# ==================== 完成汇总 ====================
echo ""
echo "========================================="
echo "  所有任务处理完毕！"
echo "  时间: $(date)"
echo "========================================="
echo ""
echo "📋 最终状态："
cat "$TODO_FILE"
echo ""

failed_count=$(ls "$LOG_DIR"/*.log 2>/dev/null | xargs grep -l "FAILED" 2>/dev/null | wc -l)
if [ "$failed_count" -gt 0 ]; then
    echo "⚠️  有 ${failed_count} 个任务失败，请查看 ${LOG_DIR}/ 下的日志"
fi