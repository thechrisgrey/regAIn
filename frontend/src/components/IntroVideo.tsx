import { useState, useRef, useCallback, useEffect } from 'react';

const VIDEO_URL = 'https://regain-media.s3.us-east-2.amazonaws.com/regain-prod.mp4';
const SESSION_KEY = 'regain-intro-seen';

export default function IntroVideo() {
  const [visible, setVisible] = useState(() => !sessionStorage.getItem(SESSION_KEY));
  const [fading, setFading] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const dismiss = useCallback(() => {
    setFading(true);
    sessionStorage.setItem(SESSION_KEY, '1');
    setTimeout(() => setVisible(false), 800);
  }, []);

  const handleEnded = useCallback(() => {
    dismiss();
  }, [dismiss]);

  // Fallback: if video fails to load, dismiss after brief pause
  const handleError = useCallback(() => {
    setTimeout(dismiss, 400);
  }, [dismiss]);

  // Keyboard: Escape to skip
  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [visible, dismiss]);

  if (!visible) return null;

  return (
    <div
      className={`fixed inset-0 z-[9999] flex items-center justify-center bg-[#1a1412] transition-opacity duration-700 ${
        fading ? 'opacity-0' : 'opacity-100'
      }`}
    >
      <video
        ref={videoRef}
        src={VIDEO_URL}
        autoPlay
        muted
        playsInline
        onEnded={handleEnded}
        onError={handleError}
        className="h-full w-full object-cover"
      />

      {/* Skip button */}
      <button
        onClick={dismiss}
        className="absolute bottom-8 right-8 rounded-full border border-white/20 bg-white/10 px-5 py-2 text-sm font-medium tracking-wide text-white/70 backdrop-blur-sm transition-all duration-200 hover:border-white/40 hover:bg-white/20 hover:text-white"
      >
        Skip
      </button>
    </div>
  );
}
