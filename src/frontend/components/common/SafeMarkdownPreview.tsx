'use client';

import MarkdownPreview, { type MarkdownPreviewProps } from '@uiw/react-markdown-preview';
import { defaultUrlTransform } from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';

type SafeMarkdownPreviewProps = Pick<
  MarkdownPreviewProps,
  'source' | 'style' | 'className' | 'wrapperElement'
>;

/** 用户与模型内容使用同一清洗边界；调用方仅能配置内容与外观。 */
export default function SafeMarkdownPreview(props: SafeMarkdownPreviewProps) {
  return (
    <MarkdownPreview
      {...props}
      urlTransform={defaultUrlTransform}
      pluginsFilter={(type, plugins) =>
        type === 'rehype' ? [...plugins, rehypeSanitize] : plugins
      }
    />
  );
}
