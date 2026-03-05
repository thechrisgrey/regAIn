/**
 * Smoke: NotFound page
 *
 * Verifies the 404 page renders correctly with:
 * - "Page not found" heading
 * - Explanatory text
 * - A link back to the dashboard
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NotFound from '../pages/NotFound';

function renderNotFound() {
  return render(
    <MemoryRouter>
      <NotFound />
    </MemoryRouter>,
  );
}

describe('Smoke: NotFound', () => {
  it('renders without crashing', () => {
    // Confirms the 404 page mounts and produces a heading
    renderNotFound();
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
  });

  it('displays "Page not found" heading', () => {
    // Users on an invalid route must see a clear 404 message
    renderNotFound();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Page not found',
    );
  });

  it('includes a link back to the dashboard', () => {
    // Users should have a clear escape hatch from the 404 page
    renderNotFound();
    const link = screen.getByText('Back to Dashboard').closest('a');
    expect(link).toBeTruthy();
    expect(link!.getAttribute('href')).toBe('/dashboard');
  });
});
