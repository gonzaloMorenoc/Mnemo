import { ArrowRight, GitPullRequest, ShieldCheck, Zap } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const highlights = [
  {
    title: "Ingesta viva desde CI",
    description:
      "Recibe runs de Playwright, Allure y JUnit vía webhook HMAC en tiempo real. Calcula huellas y agrupa fallos en familias de defecto entre proyectos y en el tiempo.",
    icon: GitPullRequest,
  },
  {
    title: "Triaje determinista con aprobación humana",
    description:
      "Veredicto automático — flaky / infra / mantenimiento / defecto real — con confianza calibrada y evidencia auditable. Los casos ambiguos se desempatan con el LLM local y siempre pasan por aprobación humana.",
    icon: Zap,
  },
  {
    title: "Privado y on-premise · 0 € de API",
    description:
      "LLM y embeddings locales (Ollama + HuggingFace). El dato del cliente nunca sale. Certificado de aseguramiento firmado + gate de release incluidos.",
    icon: ShieldCheck,
  },
];

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 md:py-12">
      <section className="rounded-3xl border border-zinc-200 bg-white/85 p-7 shadow-[0_2px_0_rgba(16,24,40,0.03),0_24px_60px_rgba(16,24,40,0.07)] backdrop-blur md:p-10">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Mnemo</p>
        <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-zinc-900 md:text-5xl">
          Autopilot de QA para consultoras. Triaje, acción y aseguramiento automáticos.
        </h1>
        <p className="mt-5 max-w-2xl text-base text-zinc-600 md:text-lg">
          Mnemo convierte los fallos de tus runs de test en conocimiento reutilizable (Defect DNA) y
          en veredictos de aseguramiento firmados — todo privado, on-premise y con coste de API 0 €.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/app/assurance" className="gap-2">
              Ver aseguramiento
              <ArrowRight size={16} />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/login">Iniciar sesión</Link>
          </Button>
        </div>
      </section>

      <section className="mt-8 grid gap-4 md:grid-cols-3">
        {highlights.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.title}>
              <CardHeader>
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-100 text-zinc-700">
                  <Icon size={16} />
                </span>
                <CardTitle className="text-base">{item.title}</CardTitle>
                <CardDescription>{item.description}</CardDescription>
              </CardHeader>
              <CardContent />
            </Card>
          );
        })}
      </section>
    </main>
  );
}
