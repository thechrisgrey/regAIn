import { useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useOnboarding } from '../hooks/useOnboarding';
import { useAuth } from '../hooks/useAuth';
import type { OnboardingData } from '../types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXPERIENCE_RANGES = [
  { value: '0-2', label: '0 \u2013 2 years' },
  { value: '3-5', label: '3 \u2013 5 years' },
  { value: '6-10', label: '6 \u2013 10 years' },
  { value: '11-15', label: '11 \u2013 15 years' },
  { value: '16+', label: '16+ years' },
];

const TRANSITION_TYPES = [
  { value: 'laid_off', label: 'Laid off / Role eliminated', persona: 'ai_displaced' as const },
  { value: 'voluntary', label: 'Voluntary career change', persona: 'career_pivoter' as const },
  { value: 'military', label: 'Military transition', persona: 'veteran' as const },
  { value: 'reentry', label: 'Re-entering workforce', persona: 'career_pivoter' as const },
];

const PRESET_SKILLS = [
  'Leadership',
  'Project Management',
  'Data Analysis',
  'Communication',
  'Technical Writing',
  'Problem Solving',
  'Team Building',
  'Strategic Planning',
  'Customer Relations',
  'Process Improvement',
];

const TRANSFERABLE = new Set([
  'Leadership', 'Communication', 'Problem Solving',
  'Team Building', 'Strategic Planning', 'Customer Relations',
]);

const TECHNICAL = new Set([
  'Data Analysis', 'Technical Writing', 'Process Improvement', 'Project Management',
]);

const CAMPAIGN_PHASES = [
  {
    name: 'Foundation',
    description: 'Build your base with quick wins that prove your skills transfer to new contexts.',
  },
  {
    name: 'Expansion',
    description: 'Take on bigger challenges, fill skill gaps, and grow your professional reach.',
  },
  {
    name: 'Launch',
    description: 'Target specific roles with a documented track record of measurable progress.',
  },
];

const STEPS = [
  { number: 1, label: 'Experience' },
  { number: 2, label: 'Direction' },
  { number: 3, label: 'Profile' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function categorizeSkills(skills: string[]) {
  const transferable: string[] = [];
  const technical: string[] = [];
  const domain: string[] = [];
  for (const skill of skills) {
    if (TRANSFERABLE.has(skill)) transferable.push(skill);
    else if (TECHNICAL.has(skill)) technical.push(skill);
    else domain.push(skill);
  }
  return { transferable, technical, domain };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StepIndicator({ current }: { current: number }) {
  return (
    <nav aria-label="Onboarding progress" className="flex items-center justify-center">
      {STEPS.map((s, i) => (
        <div key={s.number} className="flex items-center">
          <div className="flex flex-col items-center">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition-colors duration-300 ${
                current > s.number
                  ? 'bg-indigo-600 text-white'
                  : current === s.number
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-200 text-slate-400'
              }`}
            >
              {current > s.number ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                s.number
              )}
            </div>
            <span
              className={`mt-1.5 text-xs font-medium transition-colors duration-300 ${
                current >= s.number ? 'text-indigo-600' : 'text-slate-400'
              }`}
            >
              {s.label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div
              className={`mx-3 mb-5 h-px w-12 sm:w-20 transition-colors duration-300 ${
                current > s.number ? 'bg-indigo-600' : 'bg-slate-200'
              }`}
            />
          )}
        </div>
      ))}
    </nav>
  );
}

function SkillChips({
  selected,
  onToggle,
  customInput,
  onCustomInputChange,
  onCustomAdd,
}: {
  selected: string[];
  onToggle: (skill: string) => void;
  customInput: string;
  onCustomInputChange: (v: string) => void;
  onCustomAdd: () => void;
}) {
  const customSkills = selected.filter(s => !PRESET_SKILLS.includes(s));

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onCustomAdd();
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {PRESET_SKILLS.map(skill => {
          const active = selected.includes(skill);
          return (
            <button
              key={skill}
              type="button"
              onClick={() => onToggle(skill)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-200 ${
                active
                  ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-300'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {skill}
            </button>
          );
        })}
        {customSkills.map(skill => (
          <button
            key={skill}
            type="button"
            onClick={() => onToggle(skill)}
            className="rounded-full bg-indigo-100 px-3.5 py-1.5 text-sm font-medium text-indigo-700 ring-1 ring-indigo-300 transition-all duration-200"
          >
            {skill}
            <span className="ml-1.5 text-indigo-400">&times;</span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          type="text"
          value={customInput}
          onChange={e => onCustomInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a custom skill..."
          className="flex-1 rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
        />
        <button
          type="button"
          onClick={onCustomAdd}
          disabled={!customInput.trim()}
          className="rounded-lg bg-slate-100 px-3.5 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Add
        </button>
      </div>
    </div>
  );
}

function SkillCategory({ label, skills }: { label: string; skills: string[] }) {
  if (skills.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {skills.map(skill => (
          <span
            key={skill}
            className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-medium text-indigo-700"
          >
            {skill}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Onboarding() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data, loading, error, submitOnboarding } = useOnboarding();

  const [step, setStep] = useState(1);

  // Step 1
  const [name, setName] = useState('');
  const [currentRole, setCurrentRole] = useState('');
  const [industry, setIndustry] = useState('');
  const [yearsExperience, setYearsExperience] = useState('');
  const [story, setStory] = useState('');
  const [transitionType, setTransitionType] = useState('');

  // Step 2
  const [targetRole, setTargetRole] = useState('');
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [customSkillInput, setCustomSkillInput] = useState('');
  const [coachNotes, setCoachNotes] = useState('');

  // Validation
  const canProceed1 = name.trim() && currentRole.trim() && transitionType;
  const canProceed2 = targetRole.trim();

  // Skill management
  const toggleSkill = (skill: string) => {
    setSelectedSkills(prev =>
      prev.includes(skill) ? prev.filter(s => s !== skill) : [...prev, skill],
    );
  };

  const addCustomSkill = () => {
    const trimmed = customSkillInput.trim();
    if (trimmed && !selectedSkills.includes(trimmed)) {
      setSelectedSkills(prev => [...prev, trimmed]);
      setCustomSkillInput('');
    }
  };

  // Build payload from form state
  const buildPayload = (): OnboardingData => {
    const persona =
      TRANSITION_TYPES.find(t => t.value === transitionType)?.persona ?? 'career_pivoter';
    return {
      email: user?.username ?? '',
      name: name.trim(),
      persona,
      targetRole: targetRole.trim(),
      skills: selectedSkills.length > 0 ? selectedSkills : undefined,
    };
  };

  const handleNext = async () => {
    if (step === 1) {
      setStep(2);
    } else if (step === 2) {
      setStep(3);
      await submitOnboarding(buildPayload());
    }
  };

  const handleRetry = () => {
    void submitOnboarding(buildPayload());
  };

  // Experience summary for results
  const experienceParts = [
    currentRole,
    industry && `in ${industry}`,
    yearsExperience && `with ${yearsExperience} years of experience`,
  ].filter(Boolean);
  const experienceSummary =
    experienceParts.length > 0
      ? `${experienceParts.join(' ')}.`
      : 'Career professional in transition.';

  const skillCategories = categorizeSkills(selectedSkills);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="mx-auto max-w-2xl py-2 sm:py-6">
      <StepIndicator current={step} />

      <div key={step} className="mt-8 animate-fade-in">
        {/* ================================================================ */}
        {/* STEP 1 — Tell us about your experience                           */}
        {/* ================================================================ */}
        {step === 1 && (
          <div className="space-y-6">
            {/* Voice banner (non-functional) */}
            <div className="flex items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 px-5 py-4 opacity-70">
              <svg
                className="h-5 w-5 shrink-0 text-slate-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                />
              </svg>
              <div>
                <p className="text-sm font-medium text-slate-500">
                  Prefer to talk? Tell your AI coach about your experience.
                </p>
                <p className="mt-0.5 text-xs text-slate-400">Coming soon</p>
              </div>
            </div>

            {/* Card */}
            <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm sm:p-8">
              <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
                Tell us about your experience
              </h2>
              <p className="mt-2 text-[15px] leading-relaxed text-slate-500">
                Take a moment to share where you've been. This helps us build a
                transition plan that fits you.
              </p>

              <div className="mt-8 space-y-6">
                {/* Name */}
                <div>
                  <label htmlFor="onb-name" className="block text-sm font-medium text-slate-700">
                    Your name
                  </label>
                  <input
                    id="onb-name"
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="First and last name"
                    className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                  />
                </div>

                {/* Role & Industry (side by side on desktop) */}
                <div className="grid gap-6 sm:grid-cols-2">
                  <div>
                    <label htmlFor="onb-role" className="block text-sm font-medium text-slate-700">
                      Most recent role
                    </label>
                    <input
                      id="onb-role"
                      type="text"
                      value={currentRole}
                      onChange={e => setCurrentRole(e.target.value)}
                      placeholder="e.g. Software QA Lead"
                      className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                    />
                  </div>
                  <div>
                    <label htmlFor="onb-industry" className="block text-sm font-medium text-slate-700">
                      Industry
                    </label>
                    <input
                      id="onb-industry"
                      type="text"
                      value={industry}
                      onChange={e => setIndustry(e.target.value)}
                      placeholder="e.g. Technology"
                      className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                    />
                  </div>
                </div>

                {/* Years of experience */}
                <div>
                  <label htmlFor="onb-years" className="block text-sm font-medium text-slate-700">
                    Years of experience
                  </label>
                  <select
                    id="onb-years"
                    value={yearsExperience}
                    onChange={e => setYearsExperience(e.target.value)}
                    className="mt-1.5 block w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-[15px] text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                  >
                    <option value="">Select a range</option>
                    {EXPERIENCE_RANGES.map(r => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* What happened? */}
                <div>
                  <label htmlFor="onb-story" className="block text-sm font-medium text-slate-700">
                    What happened?
                  </label>
                  <p className="mt-0.5 text-xs text-slate-400">
                    Share as much or as little as you're comfortable with.
                  </p>
                  <textarea
                    id="onb-story"
                    value={story}
                    onChange={e => setStory(e.target.value)}
                    rows={4}
                    placeholder="I was a software QA lead for 8 years and got laid off when they automated our testing pipeline."
                    className="mt-1.5 block w-full resize-none rounded-lg border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                  />
                </div>

                {/* Transition type */}
                <fieldset>
                  <legend className="block text-sm font-medium text-slate-700">
                    What best describes your situation?
                  </legend>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    {TRANSITION_TYPES.map(t => {
                      const active = transitionType === t.value;
                      return (
                        <label
                          key={t.value}
                          className={`flex cursor-pointer items-center gap-3 rounded-xl border-2 p-4 transition-all duration-200 ${
                            active
                              ? 'border-indigo-600 bg-indigo-50/60'
                              : 'border-slate-200 bg-white hover:border-slate-300'
                          }`}
                        >
                          <input
                            type="radio"
                            name="transitionType"
                            value={t.value}
                            checked={active}
                            onChange={() => setTransitionType(t.value)}
                            className="sr-only"
                          />
                          <span
                            className={`flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                              active ? 'border-indigo-600' : 'border-slate-300'
                            }`}
                          >
                            {active && <span className="h-2 w-2 rounded-full bg-indigo-600" />}
                          </span>
                          <span
                            className={`text-sm font-medium ${
                              active ? 'text-indigo-700' : 'text-slate-700'
                            }`}
                          >
                            {t.label}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================ */}
        {/* STEP 2 — Where do you want to go?                                */}
        {/* ================================================================ */}
        {step === 2 && (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm sm:p-8">
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
              Where do you want to go?
            </h2>
            <p className="mt-2 text-[15px] leading-relaxed text-slate-500">
              Now let's look forward. What kind of work excites you?
            </p>

            <div className="mt-8 space-y-6">
              {/* Target role */}
              <div>
                <label htmlFor="onb-target" className="block text-sm font-medium text-slate-700">
                  Target role or direction
                </label>
                <p className="mt-0.5 text-xs text-slate-400">
                  This can be specific or exploratory.
                </p>
                <input
                  id="onb-target"
                  type="text"
                  value={targetRole}
                  onChange={e => setTargetRole(e.target.value)}
                  placeholder='e.g. "AI Quality Assurance Engineer" or "something in data"'
                  className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                />
              </div>

              {/* Skills */}
              <div>
                <label className="block text-sm font-medium text-slate-700">
                  Skills you want to leverage
                </label>
                <p className="mt-0.5 mb-3 text-xs text-slate-400">
                  Select from common transferable skills or add your own.
                </p>
                <SkillChips
                  selected={selectedSkills}
                  onToggle={toggleSkill}
                  customInput={customSkillInput}
                  onCustomInputChange={setCustomSkillInput}
                  onCustomAdd={addCustomSkill}
                />
              </div>

              {/* Coach notes */}
              <div>
                <label htmlFor="onb-notes" className="block text-sm font-medium text-slate-700">
                  Anything else your coach should know?
                </label>
                <p className="mt-0.5 text-xs text-slate-400">Optional</p>
                <textarea
                  id="onb-notes"
                  value={coachNotes}
                  onChange={e => setCoachNotes(e.target.value)}
                  rows={3}
                  placeholder="Schedule constraints, learning preferences, accessibility needs..."
                  className="mt-1.5 block w-full resize-none rounded-lg border border-slate-200 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-shadow"
                />
              </div>
            </div>
          </div>
        )}

        {/* ================================================================ */}
        {/* STEP 3 — Results                                                 */}
        {/* ================================================================ */}
        {step === 3 && (
          <>
            {/* Loading */}
            {(loading || (!data && !error)) && (
              <div className="flex flex-col items-center justify-center py-20">
                <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-slate-200 border-t-indigo-600" />
                <p className="mt-6 text-lg font-medium text-slate-700">
                  Building your transition profile
                </p>
                <p className="mt-1.5 text-sm text-slate-400">
                  This usually takes a few seconds...
                </p>
              </div>
            )}

            {/* Error */}
            {error && !loading && (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-6 sm:p-8 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
                  <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                  </svg>
                </div>
                <p className="mt-4 text-base font-medium text-red-800">
                  Something went wrong
                </p>
                <p className="mt-1 text-sm text-red-600">{error}</p>
                <button
                  type="button"
                  onClick={handleRetry}
                  className="mt-6 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-red-700 transition-colors"
                >
                  Try again
                </button>
              </div>
            )}

            {/* Success */}
            {data && !loading && (
              <div className="space-y-6">
                {/* Header */}
                <div className="text-center">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
                    <svg className="h-6 w-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
                    Your profile is ready
                  </h2>
                  <p className="mt-1.5 text-[15px] text-slate-500">
                    Here's what we built from your experience.
                  </p>
                </div>

                {/* Experience summary */}
                <div className="rounded-xl border border-slate-200/80 bg-slate-50 p-5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Your Background
                  </p>
                  <p className="mt-2 text-[15px] leading-relaxed text-slate-700">
                    {experienceSummary}
                  </p>
                  {(data.profile.targetRole || targetRole) && (
                    <p className="mt-1 text-[15px] text-slate-700">
                      Targeting a transition into{' '}
                      <span className="font-medium text-indigo-700">
                        {data.profile.targetRole || targetRole}
                      </span>
                      .
                    </p>
                  )}
                </div>

                {/* Skills */}
                {selectedSkills.length > 0 && (
                  <div className="rounded-xl border border-slate-200/80 bg-white p-5">
                    <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Your Skills
                    </p>
                    <div className="space-y-4">
                      <SkillCategory label="Transferable" skills={skillCategories.transferable} />
                      <SkillCategory label="Technical" skills={skillCategories.technical} />
                      <SkillCategory label="Domain" skills={skillCategories.domain} />
                    </div>
                  </div>
                )}

                {/* Campaign Roadmap */}
                <div>
                  <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Your Campaign Roadmap
                  </p>
                  <div className="grid gap-4 sm:grid-cols-3">
                    {CAMPAIGN_PHASES.map((phase, i) => {
                      const isCurrent = i === 0;
                      return (
                        <div
                          key={phase.name}
                          className={`rounded-xl border p-5 transition-shadow ${
                            isCurrent
                              ? 'border-indigo-300 bg-indigo-50/60 shadow-sm'
                              : 'border-slate-200 bg-white'
                          }`}
                        >
                          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                            Phase {i + 1}
                          </p>
                          <p
                            className={`mt-1 text-lg font-semibold ${
                              isCurrent ? 'text-indigo-700' : 'text-slate-700'
                            }`}
                          >
                            {phase.name}
                          </p>
                          <p className="mt-2 text-sm leading-relaxed text-slate-500">
                            {phase.description}
                          </p>
                          {isCurrent && (
                            <span className="mt-3 inline-block rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-semibold text-indigo-600">
                              Current Phase
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Start button */}
                <div className="pt-2 text-center">
                  <button
                    type="button"
                    onClick={() => navigate('/dashboard')}
                    className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-8 py-3 text-base font-semibold text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:ring-offset-2 transition-colors"
                  >
                    Start Your Campaign
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                    </svg>
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ================================================================ */}
      {/* Navigation buttons (steps 1 & 2 only)                            */}
      {/* ================================================================ */}
      {step < 3 && (
        <div className="mt-8 flex items-center justify-between">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep(1)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
              Back
            </button>
          ) : (
            <div />
          )}
          <button
            type="button"
            onClick={() => void handleNext()}
            disabled={step === 1 ? !canProceed1 : !canProceed2}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Next
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
