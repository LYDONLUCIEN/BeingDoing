'use client';

/**
 * Rumination v4 开场弹窗（2026-08-10）
 *
 * 每个激活码首次进入 rumination v4 页面时展示一次（后端 state.intro_shown 持久化，
 * 跨设备生效），点「确定」关闭并由父组件落标记。
 * 弹层样式与 TeamAnalysisNoticeModal 一致（AnimatePresence + z-[230]）。
 */

import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles } from 'lucide-react';

export type V4IntroModalProps = {
  open: boolean;
  onConfirm: () => void;
};

export default function V4IntroModal({ open, onConfirm }: V4IntroModalProps) {
  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[230] flex items-center justify-center px-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" aria-hidden />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="v4-intro-title"
            className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl sm:p-7"
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: 8 }}
          >
            <div className="mb-4 flex items-center gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-500 ring-1 ring-amber-100/80"
                aria-hidden
              >
                <Sparkles className="h-5 w-5" />
              </div>
              <h2
                id="v4-intro-title"
                className="text-lg font-semibold tracking-tight text-stone-800"
              >
                很高兴再次见到你！
              </h2>
            </div>

            <div className="mb-6 space-y-3 text-[15px] leading-relaxed text-stone-600">
              <p>
                先给你一个大大的“恭喜”——走到今天这一步，说明你已经对自己有了非常深入的觉察。这是我们最后一轮对话，今天的目的很简单：
                <span className="font-medium text-stone-800">
                  我们要一起做出最终的方向选择。
                </span>
              </p>
              <p className="font-medium text-stone-800">具体操作分两步：</p>
              <ol className="list-decimal space-y-2 pl-5">
                <li>
                  请你从我之前梳理出的“热爱清单”和“优势清单”里，选出最让你心动的“热爱×优势”组合——这是你未来最可持续的动力引擎。
                </li>
                <li>
                  带着这个组合，我们头脑风暴所有可能的方向，包括你想到过的、没想到过的、甚至跨界的选项。我会给你提供现实的参照和建议，然后由你来做最后的决定。
                </li>
              </ol>
              <p className="font-medium text-stone-800">准备好了吗？我们开始吧！</p>
            </div>

            <button
              type="button"
              onClick={onConfirm}
              className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800"
            >
              确定
            </button>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
