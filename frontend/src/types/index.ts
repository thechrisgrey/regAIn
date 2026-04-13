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
  items?: Mission[];
  nextCursor: string | null;
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
  items?: Evidence[];
  nextCursor: string | null;
}

export interface DashboardResponse {
  campaign: Campaign;
  stats: {
    missionsCompleted: number;
    evidenceCount: number;
    currentPhase: Campaign['phase'];
  };
  deletedAt?: string;
  deletionScheduledFor?: string;
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
  items?: VoicePracticeSession[];
  nextCursor: string | null;
}

// O*NET types (v2 API)

export interface OnetSearchResult {
  code: string;
  title: string;
  href?: string;
  tags?: { bright_outlook?: boolean; green?: boolean; apprenticeship?: boolean };
}

export interface OnetSearchResponse {
  career: OnetSearchResult[];
  total?: number;
  start?: number;
  end?: number;
}

export interface OnetKnowledgeElement {
  id: string;
  name: string;
}

export interface OnetKnowledgeGroup {
  id: string;
  name: string;
  element: OnetKnowledgeElement[];
}

export interface OnetTask {
  statement: string;
}

export interface OnetJobZone {
  code: number;
  title: string;
  experience?: string;
  training?: string;
  education?: string;
}

export interface OnetEducation {
  job_zone: OnetJobZone;
  education_usually_needed?: string[];
}

export interface OnetSalary {
  soc_code?: string;
  annual_median?: number;
  annual_10th_percentile?: number;
  annual_90th_percentile?: number;
}

export interface OnetOutlook {
  category?: string;
  description?: string;
}

export interface OnetJobOutlook {
  outlook?: OnetOutlook;
  bright_outlook?: { code: string; title: string }[];
  salary?: OnetSalary;
}

export interface OnetPersonalityType {
  id: string;
  name: string;
  description?: string;
}

export interface OnetWorkStyle {
  id: string;
  name: string;
}

export interface OnetPersonality {
  top_interest?: OnetPersonalityType;
  work_styles?: OnetWorkStyle[];
}

export interface OnetTechExample {
  title: string;
  hot_technology?: boolean;
}

export interface OnetTechnology {
  code: number;
  title: string;
  example: OnetTechExample[];
}

export interface OnetStateOutlook {
  code: string;
  name: string;
  job_outlook: string;
}

export interface OnetRelatedCareer {
  code: string;
  title: string;
  tags?: { bright_outlook?: boolean; green?: boolean };
}

export interface OnetCareerReport {
  code: string;
  title: string;
  tags?: { bright_outlook?: boolean; green?: boolean; apprenticeship?: boolean };
  what_they_do?: string;
  on_the_job?: { task: OnetTask[] };
  education?: OnetEducation | null;
  job_outlook?: OnetJobOutlook | null;
  knowledge?: OnetKnowledgeGroup[] | null;
  skills?: OnetKnowledgeGroup[] | null;
  abilities?: OnetKnowledgeGroup[] | null;
  personality?: OnetPersonality | null;
  technology?: OnetTechnology[] | null;
  check_out_my_state?: OnetStateOutlook[] | null;
  explore_more?: { careers: OnetRelatedCareer[] } | null;
}

// Analytics types

export interface SkillBreakdownItem {
  skill: string;
  count: number;
  ratio: number;
}

export interface ActivityHeatmapDay {
  date: string;
  count: number;
}

export interface VelocityWeek {
  weekStart: string;
  weekEnd: string;
  completed: number;
}

export interface CampaignEta {
  estimatedDaysRemaining: number;
  completionRate: number;
  dailyRate: number;
  confidence: 'high' | 'medium' | 'low';
}

export interface AnalyticsResponse {
  skillBreakdown: SkillBreakdownItem[];
  activityHeatmap: ActivityHeatmapDay[];
  velocityTrend: { weeks: VelocityWeek[] };
  campaignEta: CampaignEta | null;
  skillSuggestions: string[];
}

export interface SkillSuggestionsResponse {
  suggestions: string[];
}

// Impact Scorecard types

export interface SkillDetail {
  skill: string;
  count: number;
  lastDate: string;
}

export interface HotSkillGap {
  skill: string;
  gap: number;
  demand: number;
}

export interface GateCriterion {
  required: number;
  current: number;
  met: boolean;
}

export interface DimensionDetail {
  missionVelocity: {
    wcr: number;
    cds: number;
    velocityTrend: number;
    categoryBreakdown: Record<string, number>;
    last7d: number;
    prior7d: number;
    totalCompleted: number;
  };
  evidenceDensity: {
    ecr: number;
    ers: number;
    stb: number;
    uniqueSkills: number;
    totalEntries: number;
    skillDetail: SkillDetail[];
  };
  marketAlignment: {
    cosine: number;
    demandMultiplier: number;
    matchedSkills: number;
    totalTargetSkills: number;
    hotSkillsGap: HotSkillGap[];
    hasMarketData: boolean;
    targetRole?: string;
  };
  phaseProgression: {
    phase: string;
    phaseIndex: number;
    gatesMet: Record<string, GateCriterion>;
    startDate: string;
  };
  adaptiveDifficulty: {
    adaptationRates: Record<string, number>;
    difficultyCeilings: Record<string, number>;
    peak_difficulty_avg: number;
    historyByCategory?: Record<string, { day: number; difficulty: number }[]>;
  };
}

export interface ScoreResponse {
  cri: number;
  missionVelocityScore: number;
  evidenceDensityScore: number;
  marketAlignmentScore: number;
  phaseProgressionScore: number;
  adaptiveDifficultyScore: number;
  dimensionDetail: DimensionDetail;
  evidenceCount: number;
  missionsCompleted: number;
  targetRole: string;
  computedAt: string;
}

export interface ScoreSnapshot {
  cri: number;
  missionVelocityScore: number;
  evidenceDensityScore: number;
  marketAlignmentScore: number;
  phaseProgressionScore: number;
  adaptiveDifficultyScore: number;
  computedAt: string;
  sk: string;
}

export interface ScoreHistoryResponse {
  snapshots: ScoreSnapshot[];
}

export interface ShareResponse {
  shortCode: string;
  url: string;
}

export interface ExportResponse {
  url: string;
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

export interface CalendarEntry {
  dateEntryId: string;
  date: string;
  category: 'task' | 'note';
  author: 'user' | 'agent';
  content: string;
  createdAt: string;
  updatedAt: string;
}

