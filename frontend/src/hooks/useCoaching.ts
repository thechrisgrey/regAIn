import { useContext } from 'react';
import { CoachingContext, type CoachingContextType } from './CoachingContext';

export type { CoachingContextType };
export type { ChatMessage, ToolStep, ConnectionStatus } from './CoachingContext';

/** Human-readable labels for tool names sent by the backend. */
export const TOOL_LABELS: Record<string, string> = {
  read_user_profile: 'Reviewing your profile',
  update_user_profile: 'Updating profile',
  get_campaign_status: 'Checking campaign status',
  create_campaign: 'Setting up campaign',
  get_current_mission: 'Looking up missions',
  generate_mission: 'Creating a mission',
  complete_mission: 'Completing mission',
  log_evidence: 'Recording evidence',
  get_evidence_summary: 'Analyzing evidence',
  get_market_insights: 'Researching market data',
  get_alignment: 'Evaluating alignment',
  recall_memory: 'Recalling conversation',
  store_memory: 'Saving notes',
};

export function useCoaching(): CoachingContextType {
  const context = useContext(CoachingContext);
  if (!context) {
    throw new Error('useCoaching must be used within CoachingProvider');
  }
  return context;
}
