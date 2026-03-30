import { AlertTriangle } from "lucide-react";

export function SafetyBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-2xl border border-accent-red/20 bg-accent-red/5 p-5">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="h-4 w-4 text-accent-red" />
        <span className="text-xs font-semibold uppercase tracking-wider text-accent-red">
          Safety Warnings
        </span>
      </div>
      <ul className="space-y-1">
        {warnings.map((w, i) => (
          <li key={i} className="text-sm text-accent-red/80">
            {w}
          </li>
        ))}
      </ul>
    </div>
  );
}
