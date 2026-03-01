import { forwardRef, type ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'destructive';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantStyles: Record<Variant, string> = {
  primary:
    'bg-primary-500 text-white shadow-sm hover:bg-primary-600 hover:shadow focus:ring-primary-500/30',
  secondary:
    'border border-neutral-200/80 bg-white text-neutral-700 hover:bg-neutral-50 hover:border-neutral-300 focus:ring-neutral-400/20',
  ghost:
    'text-neutral-500 hover:text-neutral-700 hover:bg-neutral-100/80 focus:ring-neutral-400/20',
  destructive:
    'bg-error-500 text-white shadow-sm hover:bg-error-600 hover:shadow focus:ring-error-500/30',
};

const sizeStyles: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-2.5 text-base',
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', className = '', disabled, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`inline-flex items-center justify-center gap-2 font-medium rounded-[var(--radius-button)] transition-colors duration-150 focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] sm:min-h-0 ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
});

export default Button;
