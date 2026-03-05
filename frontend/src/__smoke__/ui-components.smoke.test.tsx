/**
 * Smoke: UI component library
 *
 * Verifies each shared UI component from the barrel export
 * renders without crashing. These are the building blocks
 * used across every page in the application.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  Button,
  Card,
  Badge,
  Input,
  Textarea,
  Select,
  SectionLabel,
  ProgressBar,
  SkeletonBlock,
} from '../components/ui';

describe('Smoke: UI Components', () => {
  it('Button renders with text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: 'Click me' })).toBeTruthy();
  });

  it('Button renders all variants without crashing', () => {
    // All 4 variants must mount successfully
    const variants = ['primary', 'secondary', 'ghost', 'destructive'] as const;
    for (const variant of variants) {
      const { unmount } = render(<Button variant={variant}>{variant}</Button>);
      expect(screen.getByText(variant)).toBeTruthy();
      unmount();
    }
  });

  it('Card renders children', () => {
    render(<Card>Card content</Card>);
    expect(screen.getByText('Card content')).toBeTruthy();
  });

  it('Card renders all variants without crashing', () => {
    const variants = ['default', 'elevated', 'accent'] as const;
    for (const variant of variants) {
      const { unmount } = render(<Card variant={variant}>{variant}</Card>);
      expect(screen.getByText(variant)).toBeTruthy();
      unmount();
    }
  });

  it('Badge renders text', () => {
    render(<Badge>Active</Badge>);
    expect(screen.getByText('Active')).toBeTruthy();
  });

  it('Input renders with label', () => {
    render(<Input label="Email" id="email" />);
    expect(screen.getByLabelText('Email')).toBeTruthy();
  });

  it('Textarea renders with label', () => {
    render(<Textarea label="Notes" id="notes" />);
    expect(screen.getByLabelText('Notes')).toBeTruthy();
  });

  it('Select renders with label', () => {
    render(
      <Select label="Category" id="cat">
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>,
    );
    expect(screen.getByLabelText('Category')).toBeTruthy();
  });

  it('SectionLabel renders text', () => {
    render(<SectionLabel>Section Title</SectionLabel>);
    expect(screen.getByText('Section Title')).toBeTruthy();
  });

  it('ProgressBar renders with value', () => {
    const { container } = render(<ProgressBar value={75} />);
    // Should produce a progress bar element in the DOM
    expect(container.firstChild).toBeTruthy();
  });

  it('SkeletonBlock renders', () => {
    const { container } = render(<SkeletonBlock className="h-4 w-20" />);
    expect(container.firstChild).toBeTruthy();
  });
});
