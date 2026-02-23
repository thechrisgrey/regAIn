import { type HTMLAttributes } from 'react';

type Variant = 'primary' | 'success' | 'warning' | 'error' | 'info' | 'default';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variantStyles: Record<Variant, string> = {
  primary: 'bg-primary-50 text-primary-700 ring-1 ring-primary-200',
  success: 'bg-success-50 text-success-700 ring-1 ring-success-500/20',
  warning: 'bg-warning-50 text-warning-600 ring-1 ring-warning-500/20',
  error: 'bg-error-50 text-error-700 ring-1 ring-error-500/20',
  info: 'bg-info-50 text-info-600 ring-1 ring-info-500/20',
  default: 'bg-neutral-50 text-neutral-600 ring-1 ring-neutral-200',
};

export default function Badge({
  variant = 'default',
  className = '',
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={`inline-block rounded-[var(--radius-badge)] px-2.5 py-0.5 text-xs font-semibold ${variantStyles[variant]} ${className}`}
      {...rest}
    >
      {children}
    </span>
  );
}
