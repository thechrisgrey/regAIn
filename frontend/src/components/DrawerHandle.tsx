interface DrawerHandleProps {
  open: boolean;
  onToggle: () => void;
}

export default function DrawerHandle({ open, onToggle }: DrawerHandleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={open ? 'Close chat panel' : 'Open chat panel'}
      className={`group flex w-4 cursor-pointer items-center justify-center border-x transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 ${
        open
          ? 'border-neutral-200 bg-surface-2 hover:bg-neutral-100'
          : 'border-primary-500 bg-primary-500 hover:bg-primary-600'
      }`}
    >
      <svg
        className={`h-5 w-5 transition-colors ${
          open
            ? 'text-neutral-400 group-hover:text-primary-500'
            : 'text-white'
        }`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        {open ? (
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
        )}
      </svg>
    </button>
  );
}
