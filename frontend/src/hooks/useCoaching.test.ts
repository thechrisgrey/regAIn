import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCoaching } from './useCoaching';

vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    coaching: {
      checkin: vi.fn(),
    },
  },
}));

import { api } from '../services/api';

const mockedCheckin = vi.mocked(api.coaching.checkin);

describe('useCoaching', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default state', () => {
    const { result } = renderHook(() => useCoaching());

    expect(result.current.response).toBeNull();
    expect(result.current.messages).toEqual([]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sends a message and updates state on success', async () => {
    mockedCheckin.mockResolvedValue({ response: 'Coach reply', userId: 'u-1' });

    const { result } = renderHook(() => useCoaching());

    await act(async () => {
      await result.current.sendMessage('Hello', 'checkin');
    });

    expect(mockedCheckin).toHaveBeenCalledWith(
      { message: 'Hello', session_type: 'checkin' },
      'mock-token',
    );
    expect(result.current.response).toBe('Coach reply');
    expect(result.current.messages).toEqual([
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Coach reply' },
    ]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('accumulates messages across multiple sends', async () => {
    mockedCheckin
      .mockResolvedValueOnce({ response: 'First reply', userId: 'u-1' })
      .mockResolvedValueOnce({ response: 'Second reply', userId: 'u-1' });

    const { result } = renderHook(() => useCoaching());

    await act(async () => {
      await result.current.sendMessage('First', 'onboarding');
    });
    await act(async () => {
      await result.current.sendMessage('Second', 'general');
    });

    expect(result.current.messages).toHaveLength(4);
    expect(result.current.response).toBe('Second reply');
  });

  it('sets error state on API failure', async () => {
    mockedCheckin.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useCoaching());

    await act(async () => {
      await result.current.sendMessage('Hello', 'checkin');
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.response).toBeNull();
    expect(result.current.messages).toEqual([]);
  });
});
