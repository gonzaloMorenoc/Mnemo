import { ShieldCheck } from "lucide-react";

/**
 * Sello del ACTA DE TRASPASO. Misma gramática visual que AuthenticityStamp:
 *  - el MARCO habla de la firma (azul MTP, neutro respecto al contenido),
 *  - el CONTENIDO habla de lo que consta dentro — aquí, la continuidad del
 *    proyecto en el momento de emitirla, no un veredicto de release.
 *
 * Solo se renderiza cuando la firma YA se ha validado: el acta llega desde una
 * URL, es decir, de un tercero cualquiera.
 */
interface Dimension {
  key: string;
  label: string;
  num: number;
  den: number;
  ratio: number | null;
  weight: number;
}

export function HandoverStamp({ canonical }: { canonical: Record<string, unknown> }) {
  const str = (v: unknown) => (typeof v === "string" ? v : "");
  // Campo ausente → raya, nunca una etiqueta huérfana ("clave " sin nada detrás).
  const conRaya = (v: string) => (v.length > 0 ? v : "—");
  const continuity = (canonical.continuity ?? {}) as Record<string, unknown>;
  const score = typeof continuity.score === "number" ? continuity.score : null;
  const dimensions = Array.isArray(continuity.dimensions)
    ? (continuity.dimensions as Dimension[])
    : [];
  const fecha = str(canonical.created_at);

  return (
    <div className="rounded-xl border-2 border-primary/30 bg-primary/[0.04] p-6">
      <div className="flex items-center gap-2 text-primary">
        <ShieldCheck className="h-6 w-6" />
        <span className="text-lg font-semibold">
          Acta de traspaso auténtica · firmada · íntegra
        </span>
      </div>
      <p className="mt-1 text-sm text-zinc-600">
        La firma garantiza integridad y origen. El estado del conocimiento es el que
        consta dentro del acta, en el momento en que se emitió.
      </p>

      <div className="mt-5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {score === null ? (
          <span className="text-sm text-zinc-600">Sin datos suficientes.</span>
        ) : (
          <>
            <span className="text-4xl font-semibold text-zinc-900">{score}</span>
            <span className="text-sm text-zinc-600">/ 100 de continuidad</span>
          </>
        )}
        <span className="text-sm font-medium text-zinc-900">
          {conRaya(str(canonical.project))}
        </span>
      </div>

      {dimensions.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-zinc-600">
          {dimensions.map((d) => (
            <li key={d.key} className="flex items-center justify-between">
              <span>{d.label}</span>
              <span>{d.den > 0 ? `${d.num} / ${d.den}` : "sin datos"}</span>
            </li>
          ))}
        </ul>
      )}

      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-zinc-500 sm:grid-cols-2">
        <div>
          emitida <span className="font-mono">{conRaya(fecha.slice(0, 10))}</span>
        </div>
        <div>
          clave <span className="font-mono">{conRaya(str(canonical.key_id))}</span>
        </div>
      </dl>
    </div>
  );
}
