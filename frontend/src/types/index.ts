// Domain models

export interface UserProfile {
  userId: string;
  email: string;
  name: string;
  persona: 'veteran' | 'ai_displaced' | 'career_pivoter';
  onboardingCompleted: boolean;
  createdAt: string;
  targetRole?: string;
  skills?: string[];
}

export interface Campaign {
  userId: string;
  campaignId: string;
  title: string;
  phase: 'foundation' | 'momentum' | 'acceleration' | 'transition';
  status: 'active' | 'paused' | 'completed';
  startDate: string;
  targetRole: string;
  skillsFocus: string[];
}

export interface Mission {
  userId: string;
  missionId: string;
  campaignId: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
  completedDate?: string;
  evidenceId?: string;
}

export interface Evidence {
  userId: string;
  evidenceId: string;
  missionId: string;
  skillTag: string;
  artifactUrl?: string;
  reflection: string;
  createdAt: string;
}

// API request types

export interface OnboardingData {
  email: string;
  name: string;
  persona: UserProfile['persona'];
  targetRole: string;
  skills?: string[];
}

export interface CompleteData {
  reflection: string;
  artifactUrl?: string;
  skillTags: string[];
}

// API response types

export interface OnboardingResponse {
  userId: string;
  campaignId: string;
  profile: UserProfile;
}

export interface MissionsResponse {
  missions: Mission[];
  dailyRemaining: number;
  dailyLimit: number;
}

export interface GenerateResponse {
  mission: Mission;
  dailyRemaining: number;
  dailyLimit: number;
}

export interface CompleteResponse {
  success: boolean;
  evidenceId: string;
}

export interface EvidenceResponse {
  evidence: Evidence[];
}

export interface DashboardResponse {
  campaign: Campaign;
  stats: {
    missionsCompleted: number;
    evidenceCount: number;
    currentPhase: Campaign['phase'];
  };
}

// Coaching types

export interface CoachingRequest {
  message: string;
  session_type: 'onboarding' | 'checkin' | 'general';
}

export interface CoachingResponse {
  response: string;
  userId: string;
}

// Voice Practice types

export type VoicePracticeSessionType = 'interview' | 'mission_discussion';

export interface VoicePracticeSession {
  userId: string;
  sessionId: string;
  sessionType: VoicePracticeSessionType;
  status: 'active' | 'completed' | 'failed';
  createdAt: string;
  completedAt?: string;
  durationSeconds: number;
  s3TranscriptKey: string;
  s3AssessmentKey: string;
  assessmentSummary: string;
  overallScore: number;
  turnCount: number;
  targetRole: string;
}

export interface VoicePracticeTranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

export interface VoicePracticeTranscript {
  sessionId: string;
  sessionType: VoicePracticeSessionType;
  turns: VoicePracticeTranscriptEntry[];
}

export interface AssessmentSection {
  title: string;
  score: number;
  feedback: string;
  suggestions: string[];
}

export interface VoicePracticeAssessment {
  overallScore: number;
  sections: AssessmentSection[];
  strengths: string[];
  areasForImprovement: string[];
  summary: string;
}

export interface VoiceSessionsResponse {
  sessions: VoicePracticeSession[];
}

export interface VoiceSessionDetailResponse {
  session: VoicePracticeSession;
  transcript: VoicePracticeTranscript | null;
  assessment: VoicePracticeAssessment | null;
}

