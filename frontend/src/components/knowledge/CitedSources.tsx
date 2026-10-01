import { Badge } from "@/components/ui/badge";
import type { CitedSource } from "@/lib/api/types";

// Las citas del LLM son ids. Sin su título, la respuesta enseñaba «· 7330f4ee-…»
// justo donde el producto promete decir de dónde sale cada respuesta.
export function CitedSources({ citations, sources = [] }: {
  citations: string[];
  sources?: CitedSource[];
}) {
  if (citations.length === 0) return null;
  const items: CitedSource[] = sources.length > 0
    ? sources
    : citations.map((id) => ({ id, type: "knowledge", title: `Fuente ${id.slice(0, 8)}` }));
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-zinc-500">Fuentes citadas</p>
      <ul className="space-y-1.5">
        {items.map((s) => (
          <li key={s.id} className="flex items-start gap-2 text-xs text-zinc-700">
            <Badge variant={s.type === "knowledge" ? "default" : "user"} className="shrink-0">
              {s.type === "knowledge" ? "Conocimiento" : "Defecto"}
            </Badge>
            <span>{s.title}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
