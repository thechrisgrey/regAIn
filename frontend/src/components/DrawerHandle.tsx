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
      className="flex w-[3px] cursor-pointer items-center justify-center bg-neutral-200 transition-colors hover:bg-neutral-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
    >
      <span className="h-[30px] w-[3px] rounded-full bg-accent-400 opacity-60 transition-opacity hover:opacity-100" />
    </button>
  );
}
