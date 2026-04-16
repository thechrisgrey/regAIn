import { useEffect, useRef, useState } from 'react';

import Button from '../ui/Button';
import { Input } from '../ui/Input';

interface EditableTargetRoleProps {
  value: string;
  onSave: (next: string) => Promise<void> | void;
}

export function EditableTargetRole({ value, onSave }: EditableTargetRoleProps) {
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState(value);
  const [draft, setDraft] = useState(value);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setCurrent(value);
  }, [value]);

  useEffect(() => {
    if (editing) {
      setDraft(current);
      setError(null);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [editing, current]);

  const trimmed = draft.trim();
  const dirty = trimmed.length > 0 && trimmed !== current;

  const cancel = () => {
    setEditing(false);
    setDraft(current);
    setError(null);
  };

  const save = async () => {
    if (!dirty || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSave(trimmed);
      setCurrent(trimmed);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save target role');
    } finally {
      setSubmitting(false);
    }
  };

  if (!editing) {
    return (
      <div className="mt-5 flex items-start gap-3">
        <p className="text-2xl font-semibold tracking-tight text-neutral-900">
          {current || 'Set a target role'}
        </p>
        <button
          type="button"
          onClick={() => setEditing(true)}
          aria-label="Edit target role"
          className="mt-1 rounded-md p-1 text-neutral-400 hover:bg-surface-2 hover:text-primary-600 transition-colors"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <path d="M13.586 3.586a2 2 0 1 1 2.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793 3 14.172V17h2.828l8.379-8.379-2.828-2.828z" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-2">
      <Input
        ref={inputRef}
        label="Target role"
        value={draft}
        maxLength={200}
        disabled={submitting}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void save();
          } else if (e.key === 'Escape') {
            e.preventDefault();
            cancel();
          }
        }}
        error={error ?? undefined}
      />
      <div className="flex gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={() => void save()}
          disabled={!dirty || submitting}
        >
          {submitting ? 'Saving…' : 'Save'}
        </Button>
        <Button variant="ghost" size="sm" onClick={cancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
