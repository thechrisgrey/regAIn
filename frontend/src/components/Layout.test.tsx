import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Layout from './Layout';

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { username: 'test-user' },
    signOut: vi.fn(),
    loading: false,
    getToken: vi.fn(),
  })),
}));

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout />
    </MemoryRouter>,
  );
}

describe('Layout navigation', () => {
  it('includes Resume nav item between Evidence and Profile (Req 9.1)', () => {
    renderLayout();

    const nav = screen.getByRole('navigation');
    const links = Array.from(nav.querySelectorAll('a'));
    const labels = links.map(link => link.textContent?.trim());

    expect(labels).toContain('Resume');

    const evidenceIdx = labels.indexOf('Evidence');
    const resumeIdx = labels.indexOf('Resume');
    const profileIdx = labels.indexOf('Profile');

    expect(evidenceIdx).toBeLessThan(resumeIdx);
    expect(resumeIdx).toBeLessThan(profileIdx);
  });
});
