"use client";

import { CertificateVerifier } from "@/components/verify/CertificateVerifier";

// Versión dentro del shell (con menú): el usuario logueado no pierde la navegación.
// La página pública /verify (sin cuenta) sigue existiendo para compartir con terceros.
export default function AppVerifyPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Verificar acta</h1>
        <p className="text-sm text-zinc-500">
          Comprueba la firma Ed25519 de un acta de aseguramiento. También puedes
          compartir el enlace público{" "}
          <a href="/verify" className="underline underline-offset-2 hover:text-zinc-900">
            /verify
          </a>{" "}
          con un cliente o auditor: se verifica sin cuenta.
        </p>
      </div>
      <CertificateVerifier />
    </div>
  );
}
