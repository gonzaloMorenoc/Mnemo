"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { generateCertificate, getCertificate, getCertificatePdf } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

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
    onSuccess: () => { toast.success("Certificado generado."); qc.invalidateQueries({ queryKey: key }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const cert = query.data;

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
          Release Assurance Certificate
          <InfoTooltip term="certificado" />
        </h2>
        <Button size="sm" variant="ghost" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? "Generando…" : "Generar certificado"}
        </Button>
      </div>
      {cert ? (
        <div className="space-y-1 text-sm text-zinc-600">
          <div className="flex items-center gap-2">
            <Badge>{cert.verdict}</Badge>
            <span className="flex items-center gap-1">
              risk score <InfoTooltip term="risk_score" />
              <strong className="text-zinc-900">{cert.risk_score}</strong>
            </span>
          </div>
          <p className="font-mono text-xs text-zinc-400 break-all">firma: {cert.signature.slice(0, 32)}…</p>
          <Button size="sm" variant="outline" onClick={handleDownloadPdf}>Descargar PDF</Button>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">Aún no hay certificado para este run.</p>
      )}
    </Card>
  );
}
