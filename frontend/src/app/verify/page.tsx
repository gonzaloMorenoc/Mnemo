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
          Verificar un acta de calidad
        </h1>
        <p className="max-w-2xl text-sm text-zinc-600">
          Pega el acta de aseguramiento de QA firmada por Mnemo. Comprobamos la firma{" "}
          <span className="font-medium">Ed25519</span> contra la clave pública, sin
          necesidad de cuenta. Si la firma es válida, el acta no ha sido alterada desde
          que se emitió.
        </p>
      </header>

      <div className="mt-6">
        <CertificateVerifier />
      </div>
    </main>
  );
}
