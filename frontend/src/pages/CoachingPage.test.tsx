import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CoachingPage from './CoachingPage';

const mockSendMessage = vi.fn().mockResolvedValue(true);
const mockClearConversation = vi.fn();
const mockSetSessionType = vi.fn();

vi.mock('../hooks/useCoaching', () => ({
  useCoaching: vi.fn(() => ({
    messages: [],
    streaming: false,
    streamingText: '',
    toolSteps: [],
    error: null,
    connectionStatus: 'connected',
    streamHint: null,
    sendMessage: mockSendMessage,
    clearConversation: mockClearConversation,
    setSessionType: mockSetSessionType,
    thinking: false,
  })),
}));

vi.mock('../hooks/useVoiceSession', () => ({
  useVoiceSession: vi.fn(() => ({
    isActive: false,
    error: null,
    fallbackToText: false,
    startSession: vi.fn(),
    stopSession: vi.fn(),
  })),
}));

import { useCoaching } from '../hooks/useCoaching';
import { useVoiceSession } from '../hooks/useVoiceSession';
const mockedUseCoaching = vi.mocked(useCoaching);
const mockedUseVoiceSession = vi.mocked(useVoiceSession);

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseCoaching.mockReturnValue({
    messages: [],
    streaming: false,
    streamingText: '',
    toolSteps: [],
    error: null,
    connectionStatus: 'connected',
    streamHint: null,
    sendMessage: mockSendMessage,
    clearConversation: mockClearConversation,
    setSessionType: mockSetSessionType,
    thinking: false,
  });
  mockedUseVoiceSession.mockReturnValue({
    isActive: false,
    error: null,
    fallbackToText: false,
    startSession: vi.fn(),
    stopSession: vi.fn(),
  });
});

describe('CoachingPage', () => {
  it('renders heading and empty state', () => {
    render(<CoachingPage />);
    expect(screen.getByText('Coaching')).toBeInTheDocument();
    expect(screen.getByText('Start a conversation with your coaching agent')).toBeInTheDocument();
  });

  it('renders session type selector with options', () => {
    render(<CoachingPage />);
    const select = screen.getByLabelText('Session') as HTMLSelectElement;
    expect(select).toBeInTheDocument();
    expect(select.value).toBe('checkin');
    const options = select.querySelectorAll('option');
    expect(options).toHaveLength(3);
  });

  it('renders message input and send button', () => {
    render(<CoachingPage />);
    expect(screen.getByLabelText('Coaching message')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument();
  });

  it('send button is disabled when input is empty', () => {
    render(<CoachingPage />);
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
  });

  it('send button is enabled when input has text', () => {
    render(<CoachingPage />);
    fireEvent.change(screen.getByLabelText('Coaching message'), {
      target: { value: 'Hello coach' },
    });
    expect(screen.getByRole('button', { name: 'Send message' })).not.toBeDisabled();
  });

  it('renders user and assistant messages', () => {
    mockedUseCoaching.mockReturnValue({
      messages: [
        { role: 'user', content: 'How is my progress?' },
        { role: 'assistant', content: 'You are doing great!' },
      ],
      streaming: false,
      streamingText: '',
      toolSteps: [],
      error: null,
      connectionStatus: 'connected',
      streamHint: null,
      sendMessage: mockSendMessage,
      clearConversation: mockClearConversation,
      setSessionType: mockSetSessionType,
      thinking: false,
    });
    render(<CoachingPage />);
    expect(screen.getByText('How is my progress?')).toBeInTheDocument();
    expect(screen.getByText('You are doing great!')).toBeInTheDocument();
  });

  it('shows clear button when messages exist and not streaming', () => {
    mockedUseCoaching.mockReturnValue({
      messages: [{ role: 'user', content: 'test' }],
      streaming: false,
      streamingText: '',
      toolSteps: [],
      error: null,
      connectionStatus: 'connected',
      streamHint: null,
      sendMessage: mockSendMessage,
      clearConversation: mockClearConversation,
      setSessionType: mockSetSessionType,
      thinking: false,
    });
    render(<CoachingPage />);
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
  });

  it('hides clear button when no messages', () => {
    render(<CoachingPage />);
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();
  });

  it('shows reconnecting banner when connection status is reconnecting', () => {
    mockedUseCoaching.mockReturnValue({
      messages: [],
      streaming: false,
      streamingText: '',
      toolSteps: [],
      error: null,
      connectionStatus: 'reconnecting',
      streamHint: null,
      sendMessage: mockSendMessage,
      clearConversation: mockClearConversation,
      setSessionType: mockSetSessionType,
      thinking: false,
    });
    render(<CoachingPage />);
    expect(screen.getByText('Reconnecting to coaching session...')).toBeInTheDocument();
  });

  it('shows disconnected banner when connection lost', () => {
    mockedUseCoaching.mockReturnValue({
      messages: [],
      streaming: false,
      streamingText: '',
      toolSteps: [],
      error: null,
      connectionStatus: 'disconnected',
      streamHint: null,
      sendMessage: mockSendMessage,
      clearConversation: mockClearConversation,
      setSessionType: mockSetSessionType,
      thinking: false,
    });
    render(<CoachingPage />);
    expect(screen.getByText('Connection lost. Messages may not be delivered.')).toBeInTheDocument();
  });

  it('shows error message when error is set', () => {
    mockedUseCoaching.mockReturnValue({
      messages: [],
      streaming: false,
      streamingText: '',
      toolSteps: [],
      error: 'WebSocket connection failed',
      connectionStatus: 'connected',
      streamHint: null,
      sendMessage: mockSendMessage,
      clearConversation: mockClearConversation,
      setSessionType: mockSetSessionType,
      thinking: false,
    });
    render(<CoachingPage />);
    expect(screen.getByText('WebSocket connection failed')).toBeInTheDocument();
  });

  it('disables input when streaming', () => {
    mockedUseCoaching.mockReturnValue({
      messages: [],
      streaming: true,
      streamingText: '',
      toolSteps: [],
      error: null,
      connectionStatus: 'connected',
      streamHint: null,
      sendMessage: mockSendMessage,
      clearConversation: mockClearConversation,
      setSessionType: mockSetSessionType,
      thinking: false,
    });
    render(<CoachingPage />);
    expect(screen.getByLabelText('Coaching message')).toBeDisabled();
  });

  it('renders voice button', () => {
    render(<CoachingPage />);
    expect(screen.getByRole('button', { name: 'Start voice session' })).toBeInTheDocument();
  });

  it('shows voice error when voice fails', () => {
    mockedUseVoiceSession.mockReturnValue({
      isActive: false,
      error: 'Microphone access denied',
      fallbackToText: false,
      startSession: vi.fn(),
      stopSession: vi.fn(),
    });
    render(<CoachingPage />);
    expect(screen.getByText('Microphone access denied')).toBeInTheDocument();
  });
});
