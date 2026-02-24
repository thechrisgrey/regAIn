// Domain models

export interface UserProfile {
  userId: string;
  email: string;
  name: string;
  firstName?: string;
  lastName?: string;
  persona: 'veteran' | 'ai_displaced' | 'career_pivoter';
  onboardingCompleted: boolean;
  createdAt: string;
  targetRole?: string;
  currentRole?: string;
  company?: string;
  industry?: string;
  yearsExperience?: string;
  yearsInRole?: string;
  highestPosition?: string;
  story?: string;
  coachNotes?: string;
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
  firstName: string;
  lastName: string;
  persona: UserProfile['persona'];
  currentRole: string;
  company?: string;
  industry?: string;
  yearsExperience?: string;
  yearsInRole?: string;
  highestPosition?: string;
  story?: string;
  targetRole: string;
  skills?: string[];
  coachNotes?: string;
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

// O*NET types

export interface OnetSearchResult {
  code: string;
  title: string;
  tags?: { bright_outlook?: boolean; green?: boolean; apprenticeship?: boolean };
}

export interface OnetSearchResponse {
  career: OnetSearchResult[];
  total?: number;
  start?: number;
  end?: number;
}

export interface OnetScoredItem {
  id: string;
  name: string;
  description?: string;
  score?: { value: number };
}

export interface OnetScoredGroup {
  title?: string;
  element: OnetScoredItem[];
}

export interface OnetTask {
  statement: string;
}

export interface OnetEducation {
  job_zone: number;
  education_usually_needed?: { category: string[] };
  experience_usually_needed?: { category: string[] };
}

export interface OnetSalary {
  annual_median?: number;
  annual_10th_percentile?: number;
  annual_25th_percentile?: number;
  annual_75th_percentile?: number;
  annual_90th_percentile?: number;
  hourly_median?: number;
}

export interface OnetOutlook {
  category?: string;
  description?: string;
}

export interface OnetPersonalityType {
  code: string;
  name: string;
  description?: string;
}

export interface OnetTechnology {
  title: { name: string };
  example: { name: string }[];
}

export interface OnetIndustry {
  code: string;
  title: string;
  percent?: number;
}

export interface OnetLocationQuotient {
  state: string;
  quotient: number;
}

export interface OnetRelatedCareer {
  code: string;
  title: string;
}

export interface OnetCareerReport {
  code: string;
  title: string;
  tags?: { bright_outlook?: boolean; green?: boolean; apprenticeship?: boolean };
  what_they_do?: string;
  on_the_job?: { task: OnetTask[] };
  education?: OnetEducation;
  outlook?: OnetOutlook;
  salary?: OnetSalary;
  knowledge?: OnetScoredGroup;
  skills?: OnetScoredGroup;
  abilities?: OnetScoredGroup;
  personality?: { top_interest?: OnetPersonalityType; secondary_interest?: OnetPersonalityType };
  technology?: { category: OnetTechnology[] };
  industry?: OnetIndustry[];
  location_quotient?: OnetLocationQuotient[];
  related_careers?: OnetRelatedCareer[];
}

export interface VoiceSessionDetailResponse {
  sessionId: string;
  sessionType: VoicePracticeSessionType;
  status: string;
  targetRole: string;
  durationSeconds: number;
  turnCount: number;
  overallScore: number;
  assessmentSummary: string;
  createdAt: string;
  transcript: VoicePracticeTranscript | VoicePracticeTranscriptEntry[] | null;
  assessment: VoicePracticeAssessment | null;
}

