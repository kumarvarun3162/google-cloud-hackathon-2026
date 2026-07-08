function Shimmer({ className }) {
  return <div className={`animate-pulse rounded-lg bg-primary/10 ${className}`} />;
}

export function StatsRowSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="flex items-center gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-primary/10"
        >
          <Shimmer className="h-10 w-10 rounded-xl" />
          <div className="flex-1">
            <Shimmer className="mb-2 h-3 w-20" />
            <Shimmer className="h-5 w-16" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function PriorityCardSkeleton() {
  return (
    <div className="flex items-center gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-primary/10">
      <Shimmer className="h-8 w-8 shrink-0 rounded-full" />
      <Shimmer className="h-14 w-14 shrink-0 rounded-full" />
      <div className="flex-1">
        <Shimmer className="mb-2 h-4 w-2/3" />
        <Shimmer className="mb-2 h-3 w-1/3" />
        <Shimmer className="h-3 w-5/6" />
      </div>
    </div>
  );
}
