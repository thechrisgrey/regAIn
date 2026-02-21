import { type HTMLAttributes } from 'react';

type Variant = 'primary' | 'success' | 'warning' | 'error' | 'info' | 'default';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variantStyles: Record<Variant, string> = {
  primary: 'bg-primary-100 text-primary-700',
  success: 'bg-success-100 text-success-700',
  warning: 'bg-warning-100 text-warning-600',
  error: 'bg-error-100 text-error-700',
  info: 'bg-info-100 text-info-600',
  default: 'bg-neutral-100 text-neutral-600',
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
