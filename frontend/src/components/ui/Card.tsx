import { type HTMLAttributes } from 'react';

type Variant = 'default' | 'elevated' | 'accent';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  hoverable?: boolean;
}

const variantStyles: Record<Variant, string> = {
  default: 'border border-neutral-200/80 bg-surface-1 shadow-card',
  elevated: 'border border-neutral-200/60 bg-surface-1 shadow-elevated',
  accent: 'border border-neutral-200/60 border-l-[3px] border-l-primary-500 bg-surface-1 shadow-card',
};

export default function Card({
  variant = 'default',
  hoverable = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={`rounded-[var(--radius-card)] ${variantStyles[variant]} ${
        hoverable
          ? 'transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5'
          : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
