/**
 * Smoke: RouteLoader
 *
 * Verifies the loading spinner component renders correctly.
 * This is used as the Suspense fallback for lazy-loaded routes.
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import RouteLoader from '../components/RouteLoader';

describe('Smoke: RouteLoader', () => {
  it('renders without crashing', () => {
    // Confirms the loader mounts and produces DOM output
    const { container } = render(<RouteLoader />);
    expect(container.firstChild).toBeTruthy();
  });

  it('contains a spinning element', () => {
    // The loader should display a visible spinner animation
    const { container } = render(<RouteLoader />);
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeTruthy();
  });
});
