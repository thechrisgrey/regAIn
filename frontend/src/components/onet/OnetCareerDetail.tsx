import type { OnetCareerReport } from '../../types';
import { Card, SectionLabel, Badge } from '../ui';
import OnetScoredSection from './OnetScoredSection';
import OnetSalaryChart from './OnetSalaryChart';

interface OnetCareerDetailProps {
  career: OnetCareerReport;
  onBack: () => void;
}

function jobZoneLabel(zone: number): string {
  const labels: Record<number, string> = {
    1: 'Little or No Preparation',
    2: 'Some Preparation',
    3: 'Medium Preparation',
    4: 'Considerable Preparation',
    5: 'Extensive Preparation',
  };
  return labels[zone] ?? `Zone ${zone}`;
}

export default function OnetCareerDetail({ career, onBack }: OnetCareerDetailProps) {
  return (
    <div className="space-y-5 animate-fade-in">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
        </svg>
        Back to results
      </button>

      {/* 1. Header */}
      <Card variant="accent" className="p-6">
        <h2 className="text-xl font-semibold tracking-tight text-neutral-900">{career.title}</h2>
        <p className="mt-1 text-sm font-mono text-neutral-500">{career.code}</p>
        {career.tags && (
          <div className="mt-3 flex flex-wrap gap-2">
            {career.tags.bright_outlook && <Badge variant="success">Bright Outlook</Badge>}
            {career.tags.green && <Badge variant="info">Green</Badge>}
            {career.tags.apprenticeship && <Badge>Apprenticeship</Badge>}
          </div>
        )}
      </Card>

      {/* 2. What They Do + Daily Tasks */}
      {(career.what_they_do || career.on_the_job?.task?.length) && (
        <Card className="p-6">
          <SectionLabel>What They Do</SectionLabel>
          {career.what_they_do && (
            <p className="mt-3 text-sm leading-relaxed text-neutral-700">{career.what_they_do}</p>
          )}
          {career.on_the_job?.task && career.on_the_job.task.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-2">
                On the Job
              </p>
              <ul className="space-y-1.5">
                {career.on_the_job.task.map((t, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-neutral-700 animate-fade-in-up"
                    style={{ animationDelay: `${i * 30}ms` }}
                  >
                    <span className="text-primary-500 mt-0.5 shrink-0">•</span>
                    {t.statement}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {/* 3. Education */}
      {career.education && (
        <Card className="p-6">
          <SectionLabel>Education</SectionLabel>
          <div className="mt-3 flex items-center gap-3">
            <Badge variant="primary">Job Zone {career.education.job_zone}</Badge>
            <span className="text-sm text-neutral-700">
              {jobZoneLabel(career.education.job_zone)}
            </span>
          </div>
          {career.education.education_usually_needed?.category && career.education.education_usually_needed.category.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-2">
                Education Usually Needed
              </p>
              <div className="flex flex-wrap gap-2">
                {career.education.education_usually_needed.category.map(cat => (
                  <Badge key={cat}>{cat}</Badge>
                ))}
              </div>
            </div>
          )}
          {career.education.experience_usually_needed?.category && career.education.experience_usually_needed.category.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-2">
                Experience Usually Needed
              </p>
              <div className="flex flex-wrap gap-2">
                {career.education.experience_usually_needed.category.map(cat => (
                  <Badge key={cat}>{cat}</Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* 4. Job Outlook + Salary */}
      {career.outlook && (
        <Card className="p-6">
          <SectionLabel>Job Outlook</SectionLabel>
          {career.outlook.category && (
            <div className="mt-3">
              <Badge variant={career.outlook.category === 'Bright' ? 'success' : 'default'}>
                {career.outlook.category}
              </Badge>
            </div>
          )}
          {career.outlook.description && (
            <p className="mt-3 text-sm leading-relaxed text-neutral-700">{career.outlook.description}</p>
          )}
        </Card>
      )}

      <OnetSalaryChart salary={career.salary} />

      {/* 5–7. Scored sections */}
      <OnetScoredSection title="Knowledge" group={career.knowledge} />
      <OnetScoredSection title="Skills" group={career.skills} />
      <OnetScoredSection title="Abilities" group={career.abilities} />

      {/* 8. Personality */}
      {career.personality && (career.personality.top_interest || career.personality.secondary_interest) && (
        <Card className="p-6">
          <SectionLabel>Personality</SectionLabel>
          <div className="mt-3 space-y-3">
            {career.personality.top_interest && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="primary">{career.personality.top_interest.name}</Badge>
                  <span className="text-xs text-neutral-400">Top interest</span>
                </div>
                {career.personality.top_interest.description && (
                  <p className="text-sm text-neutral-600">{career.personality.top_interest.description}</p>
                )}
              </div>
            )}
            {career.personality.secondary_interest && (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Badge>{career.personality.secondary_interest.name}</Badge>
                  <span className="text-xs text-neutral-400">Secondary interest</span>
                </div>
                {career.personality.secondary_interest.description && (
                  <p className="text-sm text-neutral-600">{career.personality.secondary_interest.description}</p>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 9. Technology */}
      {career.technology?.category && career.technology.category.length > 0 && (
        <Card className="p-6">
          <SectionLabel>Technology</SectionLabel>
          <div className="mt-3 space-y-3">
            {career.technology.category.map(tech => (
              <div key={tech.title.name}>
                <p className="text-sm font-medium text-neutral-700">{tech.title.name}</p>
                {tech.example?.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {tech.example.map(ex => (
                      <Badge key={ex.name} variant="default">{ex.name}</Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 10. Industries */}
      {career.industry && career.industry.length > 0 && (
        <Card className="p-6">
          <SectionLabel>Top Industries</SectionLabel>
          <div className="mt-3 space-y-2">
            {career.industry.map(ind => (
              <div key={ind.code} className="flex items-center justify-between">
                <span className="text-sm text-neutral-700">{ind.title}</span>
                {ind.percent != null && (
                  <span className="text-xs font-mono tabular-nums text-neutral-400">{ind.percent}%</span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 11. Location Quotient */}
      {career.location_quotient && career.location_quotient.length > 0 && (
        <Card className="p-6">
          <SectionLabel>Top Locations</SectionLabel>
          <div className="mt-3 space-y-2">
            {career.location_quotient.slice(0, 10).map(loc => (
              <div key={loc.state} className="flex items-center justify-between">
                <span className="text-sm text-neutral-700">{loc.state}</span>
                <span className="text-xs font-mono tabular-nums text-neutral-400">
                  {loc.quotient.toFixed(2)}x
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 12. Related Careers */}
      {career.related_careers && career.related_careers.length > 0 && (
        <Card className="p-6">
          <SectionLabel>Related Careers</SectionLabel>
          <div className="mt-3 flex flex-wrap gap-2">
            {career.related_careers.map(rc => (
              <Badge key={rc.code} variant="default">
                {rc.title}
              </Badge>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
