import { ArrowRight, BrainCircuit, Plug, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/card";

const highlights = [
  {
    title: "Acta firmada verificable",
    description:
      "El veredicto de cada run, sellado criptográficamente. Cliente y auditor pueden comprobar su integridad y origen — sin cuenta.",
    icon: ShieldCheck,
  },
  {
    title: "Memoria que aprende",
    description:
      "Cada corrección de tu equipo calibra el motor de triaje. Lo aprendido responde preguntas, alimenta planes de prueba y detecta huecos de cobertura.",
    icon: BrainCircuit,
  },
  {
    title: "Se enchufa a tu CI",
    description:
      "JUnit, Playwright, Allure y cuatro formatos más, con un token. Sin instalar nada en el repositorio.",
    icon: Plug,
  },
];

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 md:py-12">
      {/* Hero: el único gesto vistoso — azul MTP con brillos celestes. */}
      <section
        className="relative overflow-hidden rounded-3xl px-7 py-14 text-white shadow-[0_24px_60px_rgba(16,18,70,0.20)] md:px-12 md:py-16"
        style={{
          background:
            "radial-gradient(680px 340px at 85% -10%, rgba(91,178,221,0.30), transparent 60%)," +
            "radial-gradient(520px 300px at -8% 115%, rgba(91,178,221,0.16), transparent 55%)," +
            "linear-gradient(135deg, #101246 0%, #171a58 55%, #101246 100%)",
        }}
      >
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-sky-300">
          Mnemo · QA Memory
        </p>
        <h1 className="mt-4 max-w-[18ch] text-balance text-4xl font-semibold leading-[1.12] tracking-tight md:text-5xl">
          Cada release, con su acta firmada.
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-white/75 md:text-lg">
          Mnemo clasifica los fallos de tus tests con reglas deterministas, aprende de cada
          corrección de tu equipo y emite un acta criptográfica que cualquiera puede verificar
          — sin cuenta.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-[#101246] transition hover:bg-sky-50"
          >
            Entrar
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/verify"
            className="inline-flex items-center rounded-xl border border-white/35 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
          >
            Verificar un acta
          </Link>
        </div>

        <div className="mt-8 inline-flex items-center gap-2 rounded-full border border-sky-300/30 px-3 py-1.5 text-xs text-sky-200">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Firma Ed25519 · verificable públicamente en /verify
        </div>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-3">
        {highlights.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.title} className="p-5">
              <span className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon size={16} />
              </span>
              <h2 className="text-base font-semibold text-zinc-900">{item.title}</h2>
              <p className="mt-1.5 text-sm text-zinc-600">{item.description}</p>
            </Card>
          );
        })}
      </section>
    </main>
  );
}
