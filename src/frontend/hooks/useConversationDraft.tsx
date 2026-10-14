'use client';

import { createContext, useContext, useMemo, useState, type ReactNode, type Dispatch, type SetStateAction } from 'react';

type Drafts = Record<string, { base: string; text: string }>;
const DraftContext = createContext<readonly [Drafts, Dispatch<SetStateAction<Drafts>>] | null>(null);

/** 页级草稿随页面卸载清除；横竖屏或多栏重排不会丢失，亦不写入浏览器持久存储。 */
export function ConversationDraftProvider({ children }: { children: ReactNode }) {
  const [drafts, setDrafts] = useState<Drafts>({});
  const value = useMemo(() => [drafts, setDrafts] as const, [drafts]);
  return <DraftContext.Provider value={value}>{children}</DraftContext.Provider>;
}

/** key 区分激活码、组合和输入种类；服务端原文变化后以新原文为准。 */
export function useConversationDraft(key: string, savedText = '') {
  const context = useContext(DraftContext);
  if (!context) throw new Error('会话草稿需要置于当前页面的 ConversationDraftProvider 内');
  const [drafts, setDrafts] = context;
  const entry = drafts[key];
  const text = entry?.base === savedText ? entry.text : savedText;
  const setText = (value: string) => {
    setDrafts((previous) => ({ ...previous, [key]: { base: savedText, text: value } }));
  };
  return [text, setText] as const;
}
