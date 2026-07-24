"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ShieldX, KeyRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getCertificatePubkey, verifyCertificate } from "@/lib/api/endpoints";
import { decodeShare } from "@/lib/certificate-share";
import { AuthenticityStamp } from "@/components/verify/AuthenticityStamp";
import { Button } from "@/components/ui/button";
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

/**
 * Núcleo de verificación (formulario + resultado + clave pública), sin cromo de
 * página. Lo usan la home pública `/verify` (sin cuenta) y `/app/verify` dentro del
 * shell — así el usuario logueado no pierde el menú.
 */
export function CertificateVerifier() {
  const [raw, setRaw] = useState("");
  const [payload, setPayload] = useState<Payload | null>(null);
  const [linkError, setLinkError] = useState("");
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
      // Verificar a mano siempre parte de cero: si el acta en pantalla venía de
      // un enlace (sello de procedencia, aviso ámbar de enlace roto), esa
      // procedencia ya no aplica al texto que el usuario acaba de pegar.
      if (!fromLink) {
        setLlegaPorEnlace(false);
        setLinkError("");
      }
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

  const valido = verify.data?.valido === true;
  const invalido = verify.isSuccess && verify.data?.valido === false;

  const formulario = (
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
  );

  const resultado = (
    <div aria-live="polite">
      {verify.isPending && <p className="text-sm text-zinc-500">Comprobando la firma…</p>}
      {verify.isError && (
        <p className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600">
          No se pudo comprobar la firma ahora mismo: no hay conexión con el servicio de
          verificación. Vuelve a intentarlo en un momento. Esto no dice nada sobre el acta.
        </p>
      )}
      {valido && payload && <AuthenticityStamp canonical={payload.canonical_json} />}
      {invalido && (
        <Card className="border-red-200 bg-red-50/60">
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
  );

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

      {llegaPorEnlace ? (
        <>
          {resultado}
          <details className="mt-6">
            <summary className="cursor-pointer text-sm text-zinc-500">
              Ver el acta que se ha verificado
            </summary>
            <div className="mt-3">{formulario}</div>
          </details>
        </>
      ) : (
        <>
          {formulario}
          <div className="mt-6">{resultado}</div>
        </>
      )}

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
