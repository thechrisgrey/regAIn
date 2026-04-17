import { memo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import type { ReactNode } from 'react';

interface MarkdownMessageProps {
  content: string;
}

const components: Components = {
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }: { children?: ReactNode }) => (
    <em className="italic">{children}</em>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="list-disc pl-5 mb-2 last:mb-0 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="list-decimal pl-5 mb-2 last:mb-0 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="leading-relaxed">{children}</li>
  ),
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="text-base font-semibold mb-1.5">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="text-base font-semibold mb-1.5">{children}</h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="text-sm font-semibold mb-1">{children}</h3>
  ),
  code: ({ className, children }: { className?: string; children?: ReactNode }) => {
    const isBlock = className?.startsWith('language-');
    if (isBlock) {
      return (
        <code className="block bg-neutral-800 text-neutral-100 rounded-[var(--radius-button)] px-3 py-2 my-2 text-xs font-mono overflow-x-auto">
          {children}
        </code>
      );
    }
    return (
      <code className="bg-neutral-200/60 text-neutral-800 rounded px-1 py-0.5 text-xs font-mono">
        {children}
      </code>
    );
  },
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="border-l-2 border-neutral-300 pl-3 my-2 text-neutral-600 italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-neutral-200 my-3" />,
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary-600 underline underline-offset-2 hover:text-primary-700"
    >
      {children}
    </a>
  ),
};

/** Convert `<thinking>...</thinking>` blocks to italicized text. */
function formatThinkingBlocks(text: string): string {
  return text.replace(
    /<thinking>([\s\S]*?)<\/thinking>/g,
    (_match, inner: string) => `*${inner.trim()}*`,
  );
}

export default memo(function MarkdownMessage({ content }: MarkdownMessageProps) {
  const processed = formatThinkingBlocks(content);
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {processed}
    </Markdown>
  );
});
