export interface ResumeSkill {
  skill_name: string;
  evidence_count: number;
  strongest_evidence_summary: string;
  proficiency_indicator: string;
}

export interface ResumeFrontmatter {
  schema_version: string;
  generated_at: string;
  regain_version: string;
  name: string;
  target_role: string;
  transition_type: string;
  skills: ResumeSkill[];
  campaign_phase: string;
  campaign_progress_pct: number;
  market_alignment_score: number;
  missions_completed: number;
  evidence_items: number;
  top_accomplishments: string[];
}

export interface ResumeResponse {
  content: string;
  generatedAt: string;
  version: number;
  downloadUrl: string;
  frontmatter: ResumeFrontmatter;
}
