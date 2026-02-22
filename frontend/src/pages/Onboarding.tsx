import { useState, useCallback, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useOnboarding } from '../hooks/useOnboarding';
import { useAuth } from '../hooks/useAuth';
import type { OnboardingData } from '../types';
import { api } from '../services/api';
import { Card, SectionLabel, Badge, Button, Input, Textarea, Select } from '../components/ui';
import VoiceOnboarding from '../components/voice/VoiceOnboarding';

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
                  ? 'bg-primary-500 text-white'
                  : current === s.number
                    ? 'bg-primary-500 text-white shadow-elevated'
                    : 'bg-neutral-200 text-neutral-400'
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
                current >= s.number ? 'text-primary-600' : 'text-neutral-400'
              }`}
            >
              {s.label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div
              className={`mx-3 mb-5 h-px w-12 sm:w-20 transition-colors duration-300 ${
                current > s.number ? 'bg-primary-500' : 'bg-neutral-200'
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
              className={`rounded-[var(--radius-badge)] px-3.5 py-1.5 text-sm font-medium transition-all duration-200 ${
                active
                  ? 'bg-primary-100 text-primary-700 ring-1 ring-primary-300'
                  : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
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
            className="rounded-[var(--radius-badge)] bg-primary-100 px-3.5 py-1.5 text-sm font-medium text-primary-700 ring-1 ring-primary-300 transition-all duration-200"
          >
            {skill}
            <span className="ml-1.5 text-primary-400">&times;</span>
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
          className="flex-1 rounded-[var(--radius-button)] border border-neutral-200 px-3.5 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 transition-shadow"
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={onCustomAdd}
          disabled={!customInput.trim()}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

function SkillCategory({ label, skills }: { label: string; skills: string[] }) {
  if (skills.length === 0) return null;
  return (
    <div>
      <SectionLabel className="mb-2">{label}</SectionLabel>
      <div className="flex flex-wrap gap-1.5">
        {skills.map(skill => (
          <Badge key={skill} variant="primary">
            {skill}
          </Badge>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const VOICE_AVAILABLE =
  !!import.meta.env.VITE_VOICE_WS_URL &&
  typeof navigator !== 'undefined' &&
  !!navigator.mediaDevices?.getUserMedia;

export default function Onboarding() {
  const navigate = useNavigate();
  const { user, getToken } = useAuth();
  const { data, loading, error, submitOnboarding } = useOnboarding();

  const [step, setStep] = useState(1);
  const [voiceMode, setVoiceMode] = useState(false);

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

  const handleVoiceSessionEnd = useCallback(async () => {
    try {
      const token = await getToken();
      await api.dashboard.get(token);
      navigate('/dashboard');
    } catch {
      setVoiceMode(false);
    }
  }, [getToken, navigate]);

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
        {/* Voice onboarding — replaces the form when active */}
        {voiceMode && step < 3 && (
          <VoiceOnboarding
            onSessionEnd={() => void handleVoiceSessionEnd()}
            onError={() => setVoiceMode(false)}
          />
        )}

        {step === 1 && !voiceMode && (
          <div className="space-y-6">
            {/* Voice onboarding banner */}
            {VOICE_AVAILABLE && (
              <button
                type="button"
                onClick={() => setVoiceMode(true)}
                className="group w-full flex items-center gap-4 rounded-[var(--radius-card)] border border-primary-200 bg-primary-50/50 px-5 py-4 transition-all duration-200 hover:bg-primary-50 hover:border-primary-300 hover:shadow-card text-left"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-100 text-primary-600 transition-colors group-hover:bg-primary-200">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2 12h2m4-6v12m4-8v4m4-10v16m4-12v8" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-neutral-700">
                    Prefer to talk? Tell your AI coach about your experience using your voice.
                  </p>
                </div>
                <svg className="h-5 w-5 shrink-0 text-neutral-400 transition-colors group-hover:text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </button>
            )}

            {/* Card */}
            <Card className="p-6 sm:p-8">
              <h2 className="text-2xl font-semibold tracking-tight text-neutral-900">
                Tell us about your experience
              </h2>
              <p className="mt-2 text-[15px] leading-relaxed text-neutral-500">
                Take a moment to share where you've been. This helps us build a
                transition plan that fits you.
              </p>

              <div className="mt-8 space-y-6">
                {/* Name */}
                <Input
                  id="onb-name"
                  label="Your name"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="First and last name"
                />

                {/* Role & Industry (side by side on desktop) */}
                <div className="grid gap-6 sm:grid-cols-2">
                  <Input
                    id="onb-role"
                    label="Most recent role"
                    value={currentRole}
                    onChange={e => setCurrentRole(e.target.value)}
                    placeholder="e.g. Software QA Lead"
                  />
                  <Input
                    id="onb-industry"
                    label="Industry"
                    value={industry}
                    onChange={e => setIndustry(e.target.value)}
                    placeholder="e.g. Technology"
                  />
                </div>

                {/* Years of experience */}
                <Select
                  id="onb-years"
                  label="Years of experience"
                  value={yearsExperience}
                  onChange={e => setYearsExperience(e.target.value)}
                >
                  <option value="">Select a range</option>
                  {EXPERIENCE_RANGES.map(r => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </Select>

                {/* What happened? */}
                <Textarea
                  id="onb-story"
                  label="What happened?"
                  hint="Share as much or as little as you're comfortable with."
                  value={story}
                  onChange={e => setStory(e.target.value)}
                  rows={4}
                  placeholder="I was a software QA lead for 8 years and got laid off when they automated our testing pipeline."
                  className="resize-none"
                />

                {/* Transition type */}
                <fieldset>
                  <legend className="block text-sm font-medium text-neutral-700">
                    What best describes your situation?
                  </legend>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    {TRANSITION_TYPES.map(t => {
                      const active = transitionType === t.value;
                      return (
                        <label
                          key={t.value}
                          className={`flex cursor-pointer items-center gap-3 rounded-[var(--radius-card)] border-2 p-4 transition-all duration-200 ${
                            active
                              ? 'border-primary-500 bg-primary-50'
                              : 'border-neutral-200 bg-white hover:border-neutral-300'
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
                              active ? 'border-primary-500' : 'border-neutral-300'
                            }`}
                          >
                            {active && <span className="h-2 w-2 rounded-full bg-primary-500" />}
                          </span>
                          <span
                            className={`text-sm font-medium ${
                              active ? 'text-primary-700' : 'text-neutral-700'
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
            </Card>
          </div>
        )}

        {/* ================================================================ */}
        {/* STEP 2 — Where do you want to go?                                */}
        {/* ================================================================ */}
        {step === 2 && !voiceMode && (
          <Card className="p-6 sm:p-8">
            <h2 className="text-2xl font-semibold tracking-tight text-neutral-900">
              Where do you want to go?
            </h2>
            <p className="mt-2 text-[15px] leading-relaxed text-neutral-500">
              Now let's look forward. What kind of work excites you?
            </p>

            <div className="mt-8 space-y-6">
              {/* Target role */}
              <div>
                <Input
                  id="onb-target"
                  label="Target role or direction"
                  value={targetRole}
                  onChange={e => setTargetRole(e.target.value)}
                  placeholder='"AI Quality Assurance Engineer" or "something in data"'
                />
                <p className="mt-1 text-xs text-neutral-400">
                  This can be specific or exploratory.
                </p>
              </div>

              {/* Skills */}
              <div>
                <label className="block text-sm font-medium text-neutral-700">
                  Skills you want to leverage
                </label>
                <p className="mt-0.5 mb-3 text-xs text-neutral-400">
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
              <Textarea
                id="onb-notes"
                label="Anything else your coach should know?"
                hint="Optional"
                value={coachNotes}
                onChange={e => setCoachNotes(e.target.value)}
                rows={3}
                placeholder="Schedule constraints, learning preferences, accessibility needs..."
                className="resize-none"
              />
            </div>
          </Card>
        )}

        {/* ================================================================ */}
        {/* STEP 3 — Results                                                 */}
        {/* ================================================================ */}
        {step === 3 && (
          <>
            {/* Loading */}
            {(loading || (!data && !error)) && (
              <div className="flex flex-col items-center justify-center py-20">
                <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-neutral-200 border-t-primary-500" />
                <p className="mt-6 text-lg font-medium text-neutral-700">
                  Building your transition profile
                </p>
                <p className="mt-1.5 text-sm text-neutral-400">
                  This usually takes a few seconds...
                </p>
              </div>
            )}

            {/* Error */}
            {error && !loading && (
              <Card className="border-error-200 bg-error-50 p-6 sm:p-8 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-error-100">
                  <svg className="h-6 w-6 text-error-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                  </svg>
                </div>
                <p className="mt-4 text-base font-medium text-error-700">
                  Something went wrong
                </p>
                <p className="mt-1 text-sm text-error-600">{error}</p>
                <Button
                  variant="destructive"
                  onClick={handleRetry}
                  className="mt-6"
                >
                  Try again
                </Button>
              </Card>
            )}

            {/* Success */}
            {data && !loading && (
              <div className="space-y-6 animate-fade-in">
                {/* Header */}
                <div className="text-center">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-success-100">
                    <svg className="h-6 w-6 text-success-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold tracking-tight text-neutral-900">
                    Your profile is ready
                  </h2>
                  <p className="mt-1.5 text-[15px] text-neutral-500">
                    Here's what we built from your experience.
                  </p>
                </div>

                {/* Experience summary */}
                <Card variant="default" className="bg-surface-2 p-5">
                  <SectionLabel>Your Background</SectionLabel>
                  <p className="mt-2 text-[15px] leading-relaxed text-neutral-700">
                    {experienceSummary}
                  </p>
                  {(data.profile.targetRole || targetRole) && (
                    <p className="mt-1 text-[15px] text-neutral-700">
                      Targeting a transition into{' '}
                      <span className="font-medium text-primary-700">
                        {data.profile.targetRole || targetRole}
                      </span>
                      .
                    </p>
                  )}
                </Card>

                {/* Skills */}
                {selectedSkills.length > 0 && (
                  <Card className="p-5">
                    <SectionLabel className="mb-4">Your Skills</SectionLabel>
                    <div className="space-y-4">
                      <SkillCategory label="Transferable" skills={skillCategories.transferable} />
                      <SkillCategory label="Technical" skills={skillCategories.technical} />
                      <SkillCategory label="Domain" skills={skillCategories.domain} />
                    </div>
                  </Card>
                )}

                {/* Campaign Roadmap */}
                <div>
                  <SectionLabel className="mb-3">Your Campaign Roadmap</SectionLabel>
                  <div className="grid gap-4 sm:grid-cols-3">
                    {CAMPAIGN_PHASES.map((phase, i) => {
                      const isCurrent = i === 0;
                      return (
                        <Card
                          key={phase.name}
                          variant={isCurrent ? 'accent' : 'default'}
                          className={`p-5 ${isCurrent ? 'shadow-card-hover' : ''}`}
                        >
                          <SectionLabel>Phase {i + 1}</SectionLabel>
                          <p
                            className={`mt-1 text-lg font-semibold ${
                              isCurrent ? 'text-primary-700' : 'text-neutral-700'
                            }`}
                          >
                            {phase.name}
                          </p>
                          <p className="mt-2 text-sm leading-relaxed text-neutral-500">
                            {phase.description}
                          </p>
                          {isCurrent && (
                            <Badge variant="primary" className="mt-3">
                              Current Phase
                            </Badge>
                          )}
                        </Card>
                      );
                    })}
                  </div>
                </div>

                {/* Start button */}
                <div className="pt-2 text-center">
                  <Button
                    size="lg"
                    onClick={() => navigate('/dashboard')}
                  >
                    Start Your Campaign
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                    </svg>
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ================================================================ */}
      {/* Navigation buttons (steps 1 & 2 only)                            */}
      {/* ================================================================ */}
      {step < 3 && !voiceMode && (
        <div className="mt-8 flex items-center justify-between">
          {step > 1 ? (
            <Button
              variant="secondary"
              onClick={() => setStep(1)}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
              Back
            </Button>
          ) : (
            <div />
          )}
          <Button
            onClick={() => void handleNext()}
            disabled={step === 1 ? !canProceed1 : !canProceed2}
          >
            Next
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
            </svg>
          </Button>
        </div>
      )}
    </div>
  );
}
