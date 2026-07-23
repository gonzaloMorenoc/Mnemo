import Link from "next/link";
import { Check, Circle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export type SetupStep = {
  n: number;
  title: string;
  description: string;
  href: string;
  cta: string;
  done: boolean;
  highlight?: boolean;
};

export function SetupChecklist({
  steps,
  loading,
}: {
  steps: SetupStep[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div data-testid="checklist-skeleton" className="space-y-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <ol className="space-y-3">
      {steps.map((s) => (
        <li key={s.n}>
          <Card
            className={`flex items-center gap-4 p-4 ${s.highlight ? "border-primary" : ""}`}
          >
            <span
              data-testid={s.done ? `step-done-${s.n}` : `step-todo-${s.n}`}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                s.done
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-zinc-100 text-zinc-400"
              }`}
              aria-label={s.done ? "Completado" : "Pendiente"}
            >
              {s.done ? <Check size={16} /> : <Circle size={16} />}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-zinc-900">
                {s.n}. {s.title}
              </p>
              <p className="text-xs text-zinc-500">{s.description}</p>
            </div>
            <Button
              asChild
              variant={s.highlight ? "default" : "outline"}
              size="sm"
            >
              <Link href={s.href}>{s.cta}</Link>
            </Button>
          </Card>
        </li>
      ))}
    </ol>
  );
}
