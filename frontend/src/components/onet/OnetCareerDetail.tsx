import type { OnetCareerReport } from '../../types';
import { Card, SectionLabel, Badge } from '../ui';
import OnetScoredSection from './OnetScoredSection';
import OnetSalaryChart from './OnetSalaryChart';

interface OnetCareerDetailProps {
  career: OnetCareerReport;
  onBack: () => void;
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

      {/* Header */}
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

      {/* What They Do + Tasks */}
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

      {/* Education */}
      {career.education && (
        <Card className="p-6">
          <SectionLabel>Education</SectionLabel>
          <div className="mt-3">
            <Badge variant="primary">Job Zone {career.education.job_zone.code}</Badge>
            <p className="mt-2 text-sm font-medium text-neutral-700">
              {career.education.job_zone.title}
            </p>
            {career.education.job_zone.education && (
              <p className="mt-1 text-sm text-neutral-600">{career.education.job_zone.education}</p>
            )}
            {career.education.job_zone.experience && (
              <p className="mt-1 text-sm text-neutral-500">{career.education.job_zone.experience}</p>
            )}
          </div>
          {career.education.education_usually_needed && career.education.education_usually_needed.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-2">
                Education Usually Needed
              </p>
              <div className="flex flex-wrap gap-2">
                {career.education.education_usually_needed.map(cat => (
                  <Badge key={cat}>{cat}</Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Job Outlook + Salary */}
      {career.job_outlook?.outlook && (
        <Card className="p-6">
          <SectionLabel>Job Outlook</SectionLabel>
          {career.job_outlook.outlook.category && (
            <div className="mt-3">
              <Badge variant={career.job_outlook.outlook.category === 'Bright' ? 'success' : 'default'}>
                {career.job_outlook.outlook.category}
              </Badge>
            </div>
          )}
          {career.job_outlook.outlook.description && (
            <p className="mt-3 text-sm leading-relaxed text-neutral-700">
              {career.job_outlook.outlook.description}
            </p>
          )}
          {career.job_outlook.bright_outlook && career.job_outlook.bright_outlook.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {career.job_outlook.bright_outlook.map(bo => (
                <Badge key={bo.code} variant="success">{bo.title}</Badge>
              ))}
            </div>
          )}
        </Card>
      )}

      <OnetSalaryChart salary={career.job_outlook?.salary} />

      {/* Knowledge, Skills, Abilities */}
      <OnetScoredSection title="Knowledge" groups={career.knowledge} />
      <OnetScoredSection title="Skills" groups={career.skills} />
      <OnetScoredSection title="Abilities" groups={career.abilities} />

      {/* Personality */}
      {career.personality && (career.personality.top_interest || career.personality.work_styles) && (
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
            {career.personality.work_styles && career.personality.work_styles.length > 0 && (
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-2">
                  Work Styles
                </p>
                <div className="flex flex-wrap gap-2">
                  {career.personality.work_styles.map(ws => (
                    <Badge key={ws.id} variant="default">{ws.name}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Technology */}
      {career.technology && career.technology.length > 0 && (
        <Card className="p-6">
          <SectionLabel>Technology</SectionLabel>
          <div className="mt-3 space-y-3">
            {career.technology.map(tech => (
              <div key={tech.code}>
                <p className="text-sm font-medium text-neutral-700">{tech.title}</p>
                {tech.example?.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {tech.example.map(ex => (
                      <Badge
                        key={ex.title}
                        variant={ex.hot_technology ? 'primary' : 'default'}
                      >
                        {ex.title}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Check Out My State */}
      {career.check_out_my_state && career.check_out_my_state.length > 0 && (
        <Card className="p-6">
          <SectionLabel>State Job Outlook</SectionLabel>
          <div className="mt-3 space-y-2 max-h-64 overflow-y-auto">
            {career.check_out_my_state
              .filter(s => s.job_outlook !== 'No data available')
              .map(loc => (
                <div key={loc.code} className="flex items-center justify-between">
                  <span className="text-sm text-neutral-700">{loc.name}</span>
                  <Badge
                    variant={
                      loc.job_outlook.includes('Many') ? 'success' :
                      loc.job_outlook.includes('Average') ? 'default' :
                      'warning'
                    }
                  >
                    {loc.job_outlook}
                  </Badge>
                </div>
              ))}
          </div>
        </Card>
      )}

      {/* Related Careers */}
      {career.explore_more?.careers && career.explore_more.careers.length > 0 && (
        <Card className="p-6">
          <SectionLabel>Related Careers</SectionLabel>
          <div className="mt-3 flex flex-wrap gap-2">
            {career.explore_more.careers.map(rc => (
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
