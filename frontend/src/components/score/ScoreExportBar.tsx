import { useState } from 'react';
import { Button } from '../ui';

interface ScoreExportBarProps {
  onExportPdf: () => Promise<string>;
  onShare: () => Promise<string>;
  visible: boolean;
}

export default function ScoreExportBar({ onExportPdf, onShare, visible }: ScoreExportBarProps) {
  const [pdfLoading, setPdfLoading] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handlePdf() {
    setPdfLoading(true);
    try {
      const url = await onExportPdf();
      window.open(url, '_blank');
    } finally {
      setPdfLoading(false);
    }
  }

  async function handleShare() {
    setShareLoading(true);
    try {
      const url = await onShare();
      setShareUrl(url);
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } finally {
      setShareLoading(false);
    }
  }

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-40 animate-fade-in">
      <div className="mx-auto max-w-2xl px-4 pb-4">
        <div className="flex items-center justify-center gap-3 rounded-[var(--radius-card)] border border-neutral-100 bg-surface-1/90 px-5 py-3 shadow-elevated backdrop-blur-sm">
          <Button
            variant="primary"
            size="sm"
            onClick={handlePdf}
            disabled={pdfLoading}
          >
            {pdfLoading ? 'Generating...' : 'Download Report'}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleShare}
            disabled={shareLoading}
          >
            {copied ? 'Link Copied' : shareLoading ? 'Generating...' : 'Share Scorecard'}
          </Button>
          {shareUrl && !copied && (
            <span className="text-xs text-neutral-400 truncate max-w-[200px]">
              {shareUrl}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
