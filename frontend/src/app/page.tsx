import { ArrowRight, ShieldCheck, UploadCloud, Zap } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const highlights = [
  {
    title: "Paste error, get actionable fix",
    description: "Run structured analysis with org-aware context in one step.",
    icon: Zap,
  },
  {
    title: "Upload team knowledge",
    description: "Send logs and docs to user or organization scope without extra setup.",
    icon: UploadCloud,
  },
  {
    title: "JWT-based secure access",
    description: "Supabase authentication with backend Bearer token validation.",
    icon: ShieldCheck,
  },
];

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 md:py-12">
      <section className="rounded-3xl border border-zinc-200 bg-white/85 p-7 shadow-[0_2px_0_rgba(16,24,40,0.03),0_24px_60px_rgba(16,24,40,0.07)] backdrop-blur md:p-10">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">TraceFix v2</p>
        <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-zinc-900 md:text-5xl">
          Modern debugging workspace for engineering teams.
        </h1>
        <p className="mt-5 max-w-2xl text-base text-zinc-600 md:text-lg">
          Move from raw stack traces to concrete fixes in seconds. Upload internal docs,
          analyze production errors, and collaborate with organization scopes.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/signup" className="gap-2">
              Start free
              <ArrowRight size={16} />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/login">Sign in</Link>
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
