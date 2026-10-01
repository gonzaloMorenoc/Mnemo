"use client";

import Link from "next/link";

import { CertificateVerifier } from "@/components/verify/CertificateVerifier";

export default function VerifyPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 md:py-12">
      <Link href="/" className="text-sm text-zinc-500 hover:text-zinc-800">
        ← Volver al inicio
      </Link>

      <header className="mt-4 space-y-2">
        <h1 className="text-2xl font-semibold text-zinc-900 sm:text-3xl">
          Verificar un acta firmada
        </h1>
        <p className="max-w-2xl text-sm text-zinc-600">
          Comprueba que un acta de Mnemo —la de un run de tests o la de un traspaso— la
          emitió Mnemo y nadie la ha tocado desde entonces. Sin cuenta: la firma (Ed25519)
          se comprueba contra la clave pública.
        </p>
      </header>

      <div className="mt-6">
        <CertificateVerifier />
      </div>
    </main>
  );
}
