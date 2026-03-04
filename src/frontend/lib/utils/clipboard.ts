/**
 * 安全复制到剪贴板（兼容 HTTP、无 clipboard API 的环境）
 */
export function copyToClipboard(text: string): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false);

  if (navigator?.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => true).catch(() => false);
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    const ok = document.execCommand('copy');
    return Promise.resolve(ok);
  } finally {
    document.body.removeChild(textarea);
  }
}
