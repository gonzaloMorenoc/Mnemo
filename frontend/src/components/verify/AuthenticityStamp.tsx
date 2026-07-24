import { ShieldCheck } from "lucide-react";

import { VerdictBadge } from "@/components/ui/verdict-badge";
import type { ExecutionManifest } from "@/lib/api/types";

/**
 * Sello de autenticidad. DOS EJES QUE NO SE MEZCLAN:
 *  - el MARCO habla de la firma (azul MTP, neutro respecto al resultado),
 *  - el CONTENIDO habla del veredicto (con su color semántico).
 * Un acta auténtica con veredicto "no-apto" no puede leerse como aprobada.
 *
 * Solo se renderiza cuando la firma YA se ha validado (regla de confianza:
 * el acta llega desde una URL, es decir, de un tercero cualquiera).
 */
export function AuthenticityStamp({ canonical }: { canonical: Record<string, unknown> }) {
  const identity = (canonical.identity ?? {}) as Record<string, unknown>;
  const verdict = typeof canonical.verdict === "string" ? canonical.verdict : "";
  const keyId = typeof identity.key_id === "string" ? identity.key_id : "";
  const manifest = canonical.execution_manifest as ExecutionManifest | null | undefined;
  const str = (v: unknown) => (typeof v === "string" ? v : "");

  return (
    <div className="rounded-xl border-2 border-primary/30 bg-primary/[0.04] p-6">
      <div className="flex items-center gap-2 text-primary">
        <ShieldCheck className="h-6 w-6" />
        <span className="text-lg font-semibold">Acta auténtica · firmada · íntegra</span>
      </div>
      <p className="mt-1 text-sm text-zinc-600">
        La firma garantiza integridad y origen. El veredicto es el que consta dentro del acta.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <VerdictBadge verdict={verdict} />
        <span className="text-sm text-zinc-600">
          riesgo{" "}
          <strong className="text-zinc-900">
            {verdict === "sin_confirmar" ? "sin determinar" : `${String(canonical.risk_score ?? "")}/100`}
          </strong>
        </span>
        <span className="text-sm font-medium text-zinc-900">{str(identity.project)}</span>
      </div>

      {manifest ? (
        <p className="mt-2 text-sm text-zinc-600">
          {manifest.total} tests · {manifest.passed} ✓ · {manifest.failed} ✗ ·{" "}
          {manifest.skipped} omitidos
        </p>
      ) : null}

      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-zinc-500 sm:grid-cols-2">
        <div>
          commit <span className="font-mono">{str(identity.commit_sha).slice(0, 12)}</span>
        </div>
        <div>
          run <span className="font-mono break-all">{str(identity.run_id)}</span>
        </div>
        <div>emitida {str(identity.created_at)}</div>
        {keyId ? (
          <div>
            firmada con la clave <span className="font-mono">{keyId}</span>
          </div>
        ) : null}
      </dl>
    </div>
  );
}
