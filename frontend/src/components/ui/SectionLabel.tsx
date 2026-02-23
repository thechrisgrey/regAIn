import { type HTMLAttributes } from 'react';

export default function SectionLabel({
  className = '',
  children,
  ...rest
}: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={`text-[11px] font-semibold uppercase tracking-widest text-neutral-500 ${className}`}
      {...rest}
    >
      {children}
    </p>
  );
}
