"use client";

import { useState } from "react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { generateCertificate, getCertificate, getCertificatePdf } from "@/lib/api/endpoints";
import { buildShareUrl } from "@/lib/certificate-share";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import type { Certificate, ExecutionManifest } from "@/lib/api/types";

export function CertificateCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ["certificate", runId];
  const query = useQuery({
    queryKey: key,
    queryFn: () => getCertificate(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
    retry: false,
  });
  const generate = useMutation({
    mutationFn: () => generateCertificate(accessToken!, runId),
    onSuccess: () => { toast.success("Acta generada y firmada."); qc.invalidateQueries({ queryKey: key }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const cert = query.data;

  // Guarda el share con el que se generó el enlace junto al enlace mismo:
  // si llega un acta nueva (otro cert.share), la comparación de abajo deja
  // de coincidir y el enlace de reserva se oculta solo, sin useEffect.
  const [enlaceManual, setEnlaceManual] = useState<{ share: string; url: string } | null>(null);
  const enlaceVigente = enlaceManual && enlaceManual.share === cert?.share ? enlaceManual.url : null;

  async function handleCopyLink() {
    const url = buildShareUrl(window.location.origin, cert!.share!);
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Enlace copiado.");
    } catch {
      // Sin contexto seguro o sin permiso: que al menos pueda copiarlo a mano.
      setEnlaceManual({ share: cert!.share!, url });
    }
  }

  async function handleDownloadPdf() {
    try {
      const blob = await getCertificatePdf(accessToken!, runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `certificate-${runId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("No se pudo descargar el PDF.");
    }
  }

  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-1 text-sm font-medium text-zinc-700">
          Acta de aseguramiento (certificado firmado)
          <InfoTooltip term="certificado" />
        </h2>
        <Button size="sm" variant="ghost" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? "Firmando…" : "Generar acta"}
        </Button>
      </div>
      <p className="text-xs text-zinc-400">
        Paso 3 — el resultado firmado: sella criptográficamente el veredicto del run;
        cualquiera puede comprobarla en «Verificar acta», sin cuenta.
      </p>
      {cert ? (
        <div className="space-y-1 text-sm text-zinc-600">
          <div className="flex items-center gap-2">
            <VerdictBadge verdict={cert.verdict} />
            <span className="flex items-center gap-1">
              riesgo <InfoTooltip term="risk_score" />
              <strong className="text-zinc-900">
                {cert.verdict === "sin_confirmar" ? "—" : `${cert.risk_score}/100`}
              </strong>
            </span>
          </div>
          <ExecutionManifestLine cert={cert} />
          {cert.verdict === "sin_confirmar" && (
            <p className="text-xs text-slate-600">
              El reporte no prueba una ejecución completa; el acta lo refleja.
            </p>
          )}
          <p className="font-mono text-xs text-zinc-400 break-all">firma: {cert.signature.slice(0, 32)}…</p>
          <Button size="sm" variant="outline" onClick={handleDownloadPdf}>Descargar PDF</Button>
          {cert.share ? (
            <div className="space-y-1 pt-1">
              <Button size="sm" variant="outline" onClick={handleCopyLink}>
                Copiar enlace de verificación
              </Button>
              <p className="text-xs text-zinc-400">
                El enlace lleva el acta completa (proyecto, commit, evidencia y calibración):
                compartirlo es publicarlo.
              </p>
              {enlaceVigente ? (
                <input
                  readOnly
                  value={enlaceVigente}
                  aria-label="Enlace de verificación"
                  onFocus={(e) => e.currentTarget.select()}
                  className="w-full rounded border border-zinc-200 px-2 py-1 font-mono text-xs text-zinc-600"
                />
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-zinc-500">Aún no hay acta para este run.</p>
      )}
    </Card>
  );
}

// El manifiesto de ejecución viaja dentro del canonical_json firmado (acta v3).
// En actas v2 no existe → no se muestra.
function ExecutionManifestLine({ cert }: { cert: Certificate }) {
  const m = (cert.canonical_json?.execution_manifest ?? null) as ExecutionManifest | null;
  if (!m) return null;
  return (
    <p className="text-xs text-zinc-500">
      {m.total} tests · {m.passed} ✓ · {m.failed} ✗ · {m.skipped} omitidos
      {m.flaky ? ` · ${m.flaky} flaky` : ""}
    </p>
  );
}
