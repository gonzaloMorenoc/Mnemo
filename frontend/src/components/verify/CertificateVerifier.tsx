"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ShieldCheck, ShieldX, KeyRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getCertificatePubkey, verifyCertificate } from "@/lib/api/endpoints";
import type { ExecutionManifest } from "@/lib/api/types";
import { decodeShare } from "@/lib/certificate-share";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

type Payload = { canonical_json: Record<string, unknown>; signature: string };

const ENLACE_ROTO =
  "Este enlace está incompleto: es probable que se cortara al copiarlo o al enviarlo por " +
  "correo. Pide que te lo reenvíen, o pega el acta aquí abajo.";

/**
 * Acepta o bien el acta completa que devuelve Mnemo ({..., canonical_json, signature})
 * o bien un objeto mínimo {canonical_json, signature}. Lanza con un mensaje humano.
 */
function extractPayload(raw: string): Payload {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("El texto pegado no es JSON válido.");
  }
  if (typeof parsed !== "object" || parsed === null) {
    throw new Error("El JSON debe ser el objeto del acta.");
  }
  const obj = parsed as Record<string, unknown>;
  const canonical = (obj.canonical_json ?? obj) as Record<string, unknown>;
  const signature = obj.signature;
  if (typeof signature !== "string" || signature.length === 0) {
    throw new Error("Falta el campo 'signature' del acta.");
  }
  if (typeof canonical !== "object" || canonical === null || !("schema" in canonical)) {
    throw new Error("No se reconoce el 'canonical_json' del acta.");
  }
  return { canonical_json: canonical, signature };
}

function asString(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

/**
 * Núcleo de verificación (formulario + resultado + clave pública), sin cromo de
 * página. Lo usan la home pública `/verify` (sin cuenta) y `/app/verify` dentro del
 * shell — así el usuario logueado no pierde el menú.
 */
export function CertificateVerifier() {
  const [raw, setRaw] = useState("");
  const [payload, setPayload] = useState<Payload | null>(null);
  const [linkError, setLinkError] = useState("");
  // Aún no se pinta aquí: lo consumirá la siguiente tarea (el sello visual
  // antes del formulario cuando el acta llega por enlace).
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [llegaPorEnlace, setLlegaPorEnlace] = useState(false);
  const hashProcesado = useRef("");

  const pubkey = useQuery({
    queryKey: ["cert-pubkey"],
    queryFn: getCertificatePubkey,
    staleTime: Infinity,
    retry: false,
  });

  const verify = useMutation({
    mutationFn: (rawActa: string) => verifyCertificate(rawActa),
    onError: (e: Error) => toast.error(e.message),
  });

  const runVerification = useCallback(
    (rawActa: string, fromLink = false) => {
      let p: Payload;
      try {
        p = extractPayload(rawActa);
      } catch (e) {
        // Un acta ilegible que venía de un ENLACE casi siempre es un enlace
        // truncado por el correo, no un fraude: no se pinta el rojo de "alterada".
        if (fromLink) setLinkError(ENLACE_ROTO);
        else toast.error((e as Error).message);
        setPayload(null);
        verify.reset();
        return;
      }
      setLinkError("");
      setPayload(p);
      // Parseamos (extractPayload) solo para VALIDAR y pintar el veredicto; para
      // verificar enviamos el texto CRUDO, sin re-serializar (ver verifyCertificate).
      verify.mutate(rawActa);
    },
    [verify],
  );

  useEffect(() => {
    const hash = window.location.hash;
    // El efecto se remonta en StrictMode (dev) y al recrearse `verify`: un
    // enlace solo se procesa una vez.
    if (!hash || hashProcesado.current === hash) return;
    hashProcesado.current = hash;
    const texto = decodeShare(hash);
    if (texto === null) {
      // Lectura única del fragmento al montar (guardada por `hashProcesado`),
      // no una sincronización continua con un sistema externo.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (hash.startsWith("#v1.")) setLinkError(ENLACE_ROTO);
      return;
    }
    setRaw(texto);
    setLlegaPorEnlace(true);
    runVerification(texto, true);
  }, [runVerification]);

  const identity = (payload?.canonical_json.identity ?? {}) as Record<string, unknown>;
  const verdict = asString(payload?.canonical_json.verdict) ?? "";
  const valido = verify.data?.valido === true;
  const invalido = verify.isSuccess && verify.data?.valido === false;

  return (
    <>
      {linkError ? (
        <div
          role="status"
          className="mb-6 rounded-lg border border-amber-200 bg-amber-50/60 p-4 text-sm text-amber-900"
        >
          {linkError}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">El acta (JSON)</CardTitle>
          <CardDescription>
            Pega el acta completa que recibiste o descargaste; se usan sus campos{" "}
            <code className="font-mono text-xs">canonical_json</code> y{" "}
            <code className="font-mono text-xs">signature</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            rows={10}
            spellCheck={false}
            placeholder='{ "canonical_json": { ... }, "signature": "..." }'
            className="font-mono text-xs"
            aria-label="Acta en formato JSON"
          />
          <Button onClick={() => runVerification(raw)} disabled={!raw.trim() || verify.isPending}>
            {verify.isPending ? "Verificando…" : "Verificar firma"}
          </Button>
        </CardContent>
      </Card>

      <div aria-live="polite">
        {verify.isPending && (
          <p className="mt-6 text-sm text-zinc-500">Comprobando la firma…</p>
        )}
        {verify.isError && (
          <p className="mt-6 rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600">
            No se pudo comprobar la firma ahora mismo: no hay conexión con el servicio de
            verificación. Vuelve a intentarlo en un momento. Esto no dice nada sobre el acta.
          </p>
        )}

        {valido && (
          <Card className="mt-6 border-emerald-200 bg-emerald-50/60">
            <CardContent className="space-y-4 pt-6">
              <div className="flex items-center gap-2 text-emerald-800">
                <ShieldCheck className="h-6 w-6" />
                <span className="text-lg font-semibold">Firma válida</span>
              </div>
              <p className="text-sm text-emerald-900/80">
                El acta es auténtica y no ha sido modificada desde su emisión. La firma
                garantiza integridad y origen; el veredicto (apto / no apto) es el que
                consta dentro del acta.
              </p>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                <Field label="Veredicto">
                  {verdict ? <VerdictBadge verdict={verdict} /> : <Badge>—</Badge>}
                </Field>
                <Field label="Riesgo">
                  {verdict === "sin_confirmar"
                    ? "—"
                    : `${String(payload?.canonical_json.risk_score ?? "—")}/100`}
                </Field>
                <Field label="Proyecto">{asString(identity.project) ?? "—"}</Field>
                <Field label="Commit">
                  <span className="font-mono text-xs">
                    {(asString(identity.commit_sha) ?? "—").slice(0, 12)}
                  </span>
                </Field>
                <Field label="Run">
                  <span className="font-mono text-xs break-all">
                    {asString(identity.run_id) ?? "—"}
                  </span>
                </Field>
                <Field label="Emitido">{asString(identity.created_at) ?? "—"}</Field>
              </dl>
              <ManifestSummary payload={payload} />
            </CardContent>
          </Card>
        )}

        {invalido && (
          <Card className="mt-6 border-red-200 bg-red-50/60">
            <CardContent className="space-y-2 pt-6">
              <div className="flex items-center gap-2 text-red-800">
                <ShieldX className="h-6 w-6" />
                <span className="text-lg font-semibold">Firma NO válida</span>
              </div>
              <p className="text-sm text-red-900/80">
                El acta ha sido alterada, está incompleta, o fue firmada con otra clave. No
                confíes en su contenido.
              </p>
            </CardContent>
          </Card>
        )}
      </div>

      <section className="mt-8">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-700">
          <KeyRound className="h-4 w-4" />
          Clave pública de firma
        </div>
        {pubkey.isError && (
          <p className="text-sm text-zinc-500">
            La clave pública no está disponible en este despliegue.
          </p>
        )}
        {pubkey.data && (
          <div className="space-y-2">
            <p className="text-xs text-zinc-500">
              Algoritmo: <span className="font-mono">{pubkey.data.algorithm}</span>. Puedes
              verificar el acta también de forma offline con esta clave.
            </p>
            <pre className="overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-50 p-3 font-mono text-[11px] text-zinc-600">
              {pubkey.data.public_key_pem}
            </pre>
          </div>
        )}
      </section>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="text-zinc-900">{children}</dd>
    </div>
  );
}

// Manifiesto de ejecución (acta v3); ausente en actas v2 → no se muestra.
function ManifestSummary({ payload }: { payload: Payload | null }) {
  const m = payload?.canonical_json.execution_manifest as ExecutionManifest | null | undefined;
  if (!m) return null;
  return (
    <p className="text-sm text-emerald-900/70">
      Ejecución: {m.total} tests · {m.passed} ✓ · {m.failed} ✗ · {m.skipped} omitidos
      {m.flaky ? ` · ${m.flaky} flaky` : ""}
    </p>
  );
}
