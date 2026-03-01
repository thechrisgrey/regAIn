import { useEffect } from 'react';
import { useResume } from '../hooks/useResume';
import type { ResumeFrontmatter } from '../types/resume';
import { Card, SectionLabel, Button, Badge, ProgressBar, SkeletonBlock, MarkdownMessage } from '../components/ui';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60)
    return `${diffMin} ${diffMin === 1 ? 'minute' : 'minutes'} ago`;
  if (diffHour < 24)
    return `${diffHour} ${diffHour === 1 ? 'hour' : 'hours'} ago`;
  if (diffDay === 1) return 'Yesterday';
  if (diffDay < 7) return `${diffDay} days ago`;
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1).replace(/_/g, ' ');
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6">
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-36" />
        <div className="mt-5 flex gap-12">
          {[1, 2, 3].map(i => (
            <div key={i}>
              <SkeletonBlock className="h-8 w-10" />
              <SkeletonBlock className="mt-1.5 h-2 w-20" />
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-28" />
        <div className="mt-5 space-y-3">
          {[1, 2, 3].map(i => (
            <SkeletonBlock key={i} className="h-3.5 w-full" />
          ))}
        </div>
      </Card>
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-32" />
        <SkeletonBlock className="mt-5 h-40 w-full" />
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function ResumeError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-neutral-900">Unable to load resume</p>
      <p className="mt-1.5 text-sm text-neutral-500">{message}</p>
      <Button onClick={onRetry} className="mt-6">
        Retry
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyResume({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <Card className="p-8">
      <div className="flex flex-col items-center py-12 text-center">
        <p className="text-xl font-semibold text-neutral-900">No resume yet</p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
          Generate your resume from completed missions and logged evidence.
          It updates automatically as you progress through your campaign.
        </p>
        <div className="mt-6">
          <Button onClick={onGenerate} disabled={generating}>
            {generating ? 'Generating...' : 'Generate Resume'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Frontmatter metadata display
// ---------------------------------------------------------------------------

function ResumeMetadata({ frontmatter }: { frontmatter: ResumeFrontmatter }) {
  return (
    <Card className="p-6">
      <SectionLabel>Resume Overview</SectionLabel>

      <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="text-3xl font-medium font-mono tabular-nums text-neutral-900">
            {frontmatter.missions_completed}
          </p>
          <p className="mt-0.5 text-xs text-neutral-400">missions completed</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="text-3xl font-medium font-mono tabular-nums text-neutral-900">
            {frontmatter.evidence_items}
          </p>
          <p className="mt-0.5 text-xs text-neutral-400">evidence items</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="text-3xl font-medium font-mono tabular-nums text-neutral-900">
            {frontmatter.market_alignment_score}%
          </p>
          <p className="mt-0.5 text-xs text-neutral-400">market alignment</p>
        </div>
      </div>

      <div className="mt-6 space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-400 w-24 shrink-0">Target role</span>
          <span className="text-sm text-neutral-900">{frontmatter.target_role}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-400 w-24 shrink-0">Phase</span>
          <Badge>{capitalize(frontmatter.campaign_phase)}</Badge>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-400 w-24 shrink-0">Progress</span>
          <div className="flex-1 max-w-xs">
            <ProgressBar value={frontmatter.campaign_progress_pct} max={100} />
          </div>
          <span className="text-xs font-mono tabular-nums text-neutral-500">
            {frontmatter.campaign_progress_pct}%
          </span>
        </div>
      </div>

      {/* Skills */}
      {frontmatter.skills.length > 0 && (
        <div className="mt-6">
          <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Skills</p>
          <div className="mt-3 space-y-2">
            {frontmatter.skills.map(skill => (
              <div key={skill.skill_name} className="flex items-start gap-3">
                <Badge>{capitalize(skill.proficiency_indicator)}</Badge>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-neutral-900">{skill.skill_name}</p>
                  <p className="text-xs text-neutral-500 truncate">{skill.strongest_evidence_summary}</p>
                </div>
                <span className="ml-auto text-xs font-mono tabular-nums text-neutral-400 shrink-0">
                  {skill.evidence_count} evidence
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top accomplishments */}
      {frontmatter.top_accomplishments.length > 0 && (
        <div className="mt-6">
          <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Top Accomplishments</p>
          <ul className="mt-3 space-y-1.5">
            {frontmatter.top_accomplishments.map((acc, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-neutral-700">
                <span className="text-primary-500 mt-0.5 shrink-0">•</span>
                {acc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Resume body (markdown)
// ---------------------------------------------------------------------------

function ResumeBody({ content }: { content: string }) {
  // Strip YAML frontmatter from content for rendering
  const body = content.replace(/^---[\s\S]*?---\s*/, '');

  return (
    <Card className="p-6">
      <SectionLabel>Resume</SectionLabel>
      <div className="mt-4 prose-sm">
        <MarkdownMessage content={body} />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ResumePage() {
  const { resume, loading, regenerating, error, fetchResume, regenerateResume } = useResume();

  useEffect(() => {
    void fetchResume();
  }, [fetchResume]);

  // Loading
  if (loading && !resume) {
    return <Skeleton />;
  }

  // Error (only show if no resume data to display)
  if (error && !resume) {
    return <ResumeError message={error} onRetry={() => void fetchResume()} />;
  }

  // Empty
  if (!resume) {
    return (
      <div className="animate-fade-in">
        <EmptyResume onGenerate={() => void regenerateResume()} generating={regenerating} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header with version + actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs text-neutral-400">
            Version {resume.version} — Generated {relativeTime(resume.generatedAt)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={resume.downloadUrl}
            download
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 transition-colors"
          >
            Download .md
          </a>
          <Button
            onClick={() => void regenerateResume()}
            disabled={regenerating}
          >
            {regenerating ? 'Regenerating…' : 'Regenerate'}
          </Button>
        </div>
      </div>

      {/* Error banner (shown inline when resume exists but action failed) */}
      {error && (
        <div className="rounded-[var(--radius-button)] bg-red-50 border border-red-200 px-4 py-3">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Frontmatter metadata */}
      <ResumeMetadata frontmatter={resume.frontmatter} />

      {/* Resume markdown body */}
      <ResumeBody content={resume.content} />
    </div>
  );
}