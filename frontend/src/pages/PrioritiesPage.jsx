import MPHeader from "../components/MPHeader";

export default function PrioritiesPage() {
  return (
    <div className="flex h-screen flex-col bg-surface">
      <MPHeader />
      <div className="flex flex-1 items-center justify-center px-6 text-center">
        <div>
          <p className="font-display text-lg font-semibold text-ink">
            Priority dashboard
          </p>
          <p className="mt-1 text-sm text-muted">
            Coming in Phase 3 — ranked issue clusters with priority scores.
          </p>
        </div>
      </div>
    </div>
  );
}
