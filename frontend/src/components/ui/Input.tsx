import { type InputHTMLAttributes, type TextareaHTMLAttributes, type SelectHTMLAttributes } from 'react';

/* ------------------------------------------------------------------ */
/* Input                                                              */
/* ------------------------------------------------------------------ */

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const baseInput =
  'block w-full rounded-[var(--radius-button)] border border-neutral-200 bg-white px-3.5 py-2.5 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 transition-shadow min-h-[44px]';

export function Input({ label, error, id, className = '', ...rest }: InputProps) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-neutral-700">
          {label}
        </label>
      )}
      <input id={id} className={`${label ? 'mt-1.5' : ''} ${baseInput} ${className}`} {...rest} />
      {error && <p className="mt-1.5 text-xs text-error-600">{error}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Textarea                                                           */
/* ------------------------------------------------------------------ */

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export function Textarea({ label, hint, error, id, className = '', ...rest }: TextareaProps) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-neutral-700">
          {label}
        </label>
      )}
      {hint && <p className="mt-0.5 text-xs text-neutral-400">{hint}</p>}
      <textarea
        id={id}
        className={`${label || hint ? 'mt-1.5' : ''} ${baseInput} resize-y ${className}`}
        {...rest}
      />
      {error && <p className="mt-1.5 text-xs text-error-600">{error}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Select                                                             */
/* ------------------------------------------------------------------ */

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

export function Select({ label, error, id, className = '', children, ...rest }: SelectProps) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-neutral-700">
          {label}
        </label>
      )}
      <select
        id={id}
        className={`${label ? 'mt-1.5' : ''} ${baseInput} ${className}`}
        {...rest}
      >
        {children}
      </select>
      {error && <p className="mt-1.5 text-xs text-error-600">{error}</p>}
    </div>
  );
}
