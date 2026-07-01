import { HelpCircle } from "lucide-react";

import { GLOSSARY } from "@/lib/glossary";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function InfoTooltip({
  term,
  content,
  label,
}: {
  term?: string;
  content?: string;
  label?: string;
}) {
  const text = content ?? (term ? GLOSSARY[term] : "") ?? "";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label ?? `Qué es: ${term ?? "ayuda"}`}
          className="inline-flex text-zinc-400 hover:text-zinc-600 align-middle"
        >
          <HelpCircle size={14} />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">{text}</TooltipContent>
    </Tooltip>
  );
}
