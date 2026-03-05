/**
 * Smoke: IntroVideo
 *
 * Verifies the intro video splash component:
 * - Shows on first visit (no sessionStorage key)
 * - Hides when sessionStorage indicates already seen
 * - Includes a skip button
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import IntroVideo from '../components/IntroVideo';

describe('Smoke: IntroVideo', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('renders video element when not previously seen', () => {
    // First-time visitors should see the intro splash
    const { container } = render(<IntroVideo />);
    const video = container.querySelector('video');
    expect(video).toBeTruthy();
  });

  it('renders skip button', () => {
    // Users must be able to skip the intro
    render(<IntroVideo />);
    expect(screen.getByText('Skip')).toBeTruthy();
  });

  it('does not render when sessionStorage key is set', () => {
    // Repeat visitors in the same session should not see the splash
    sessionStorage.setItem('regain-intro-seen', '1');

    const { container } = render(<IntroVideo />);
    const video = container.querySelector('video');
    expect(video).toBeNull();
  });
});
