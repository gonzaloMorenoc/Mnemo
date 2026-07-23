import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionHref?: string;
  actionLabel?: string;
}

/** Estado vacío con salida: qué es esto + qué hacer para que deje de estar vacío. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  actionHref,
  actionLabel,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-zinc-200 bg-zinc-50/60 px-6 py-10 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-400 shadow-sm">
        <Icon size={20} />
      </span>
      <div className="space-y-1">
        <p className="text-sm font-medium text-zinc-900">{title}</p>
        <p className="mx-auto max-w-sm text-sm text-zinc-500">{description}</p>
      </div>
      {actionHref && actionLabel && (
        <Button asChild variant="outline" size="sm" className="mt-1">
          <Link href={actionHref}>{actionLabel}</Link>
        </Button>
      )}
    </div>
  );
}
