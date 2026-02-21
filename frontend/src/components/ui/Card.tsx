import { type HTMLAttributes } from 'react';

type Variant = 'default' | 'elevated' | 'accent';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  hoverable?: boolean;
}

const variantStyles: Record<Variant, string> = {
  default: 'border border-neutral-200 bg-surface-1 shadow-card',
  elevated: 'border border-neutral-200 bg-surface-1 shadow-elevated',
  accent: 'border border-primary-300/40 bg-surface-1 shadow-card',
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
          ? 'transition-all duration-200 hover:shadow-card-hover hover:-translate-y-px'
          : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
