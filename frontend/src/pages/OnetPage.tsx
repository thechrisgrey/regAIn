import { useState } from 'react';
import { useOnet } from '../hooks/useOnet';
import { Card, Badge, Button, Input, SkeletonBlock } from '../components/ui';
import OnetCareerDetail from '../components/onet/OnetCareerDetail';

function SearchSkeleton() {
  return (
    <div className="space-y-3 mt-6">
      {[1, 2, 3].map(i => (
        <Card key={i} className="p-5">
          <SkeletonBlock className="h-4 w-48" />
          <SkeletonBlock className="mt-2 h-3 w-24" />
        </Card>
      ))}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-5 mt-4">
      <Card className="p-6">
        <SkeletonBlock className="h-6 w-64" />
        <SkeletonBlock className="mt-2 h-3 w-32" />
      </Card>
      {[1, 2, 3].map(i => (
        <Card key={i} className="p-6">
          <SkeletonBlock className="h-3 w-28" />
          <SkeletonBlock className="mt-4 h-20 w-full" />
        </Card>
      ))}
    </div>
  );
}

export default function OnetPage() {
  const {
    results,
    careerDetail,
    loading,
    detailLoading,
    error,
    searchCareers,
    fetchCareerDetail,
    clearDetail,
  } = useOnet();
  const [keyword, setKeyword] = useState('');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (keyword.trim()) {
      void searchCareers(keyword.trim());
    }
  };

  const handleCareerClick = (code: string) => {
    void fetchCareerDetail(code);
  };

  // Detail view
  if (detailLoading) {
    return (
      <div className="animate-fade-in">
        <DetailSkeleton />
      </div>
    );
  }

  if (careerDetail) {
    return <OnetCareerDetail career={careerDetail} onBack={clearDetail} />;
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Career Explorer
        </h1>
        <p className="mt-1 text-sm text-neutral-500">
          Search civilian careers by keyword. Powered by O*NET.
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <div className="flex-1">
          <Input
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder="Search careers (e.g. software engineer, nurse, analyst)"
          />
        </div>
        <Button type="submit" disabled={loading || !keyword.trim()}>
          {loading ? 'Searching...' : 'Search'}
        </Button>
      </form>

      {/* Error */}
      {error && (
        <div className="mt-4 rounded-[var(--radius-button)] bg-error-50 border border-error-200 px-4 py-3">
          <p className="text-sm text-error-700">{error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && <SearchSkeleton />}

      {/* Results */}
      {!loading && results.length > 0 && (
        <div className="mt-6 space-y-3">
          {results.map((career, i) => (
            <Card
              key={career.code}
              hoverable
              className="p-5 cursor-pointer animate-fade-in-up"
              style={{ animationDelay: `${i * 40}ms` }}
              onClick={() => handleCareerClick(career.code)}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-neutral-900">{career.title}</p>
                  <p className="mt-1 text-xs font-mono text-neutral-400">{career.code}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {career.tags?.bright_outlook && <Badge variant="success">Bright Outlook</Badge>}
                  {career.tags?.green && <Badge variant="info">Green</Badge>}
                  {career.tags?.apprenticeship && <Badge>Apprenticeship</Badge>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Empty state after search */}
      {!loading && results.length === 0 && keyword && !error && (
        <div className="mt-12 text-center">
          <p className="text-sm text-neutral-500">No careers found. Try a different keyword.</p>
        </div>
      )}

      {/* Initial empty state */}
      {!loading && results.length === 0 && !keyword && !error && (
        <div className="mt-16 text-center">
          <p className="text-sm text-neutral-500">
            Enter a keyword above to explore civilian career paths.
          </p>
        </div>
      )}
    </div>
  );
}
