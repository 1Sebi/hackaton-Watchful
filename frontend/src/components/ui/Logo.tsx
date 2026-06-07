// Brand wordmark, rendered as crisp HTML text (theme-able, no raster blur) to
// match `public/the-place-mamaia.svg`. Bold lowercase "the place" with spaced
// "mamaia" beneath — the anchor of the redesign's identity.
export default function Logo({ className = "" }: { className?: string }) {
  return (
    <div className={`select-none leading-none ${className}`} aria-label="the place mamaia">
      <div className="font-display text-[19px] font-black tracking-[-0.03em] text-white">
        the&nbsp;place
      </div>
      <div className="mt-0.5 text-center font-display text-[10px] font-normal tracking-[0.34em] text-slate-300">
        mamaia
      </div>
    </div>
  );
}
