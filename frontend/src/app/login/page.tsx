"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthCard } from "@/components/auth/auth-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

const schema = z.object({
  email: z.string().email("Introduce un email válido"),
  password: z.string().min(6, "La contraseña necesita al menos 6 caracteres"),
});

type LoginFormValues = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { session, configured } = useAuth();
  const nextPath = searchParams.get("next") || "/app/assurance";

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  useEffect(() => {
    if (session) {
      router.replace(nextPath);
    }
  }, [nextPath, router, session]);

  const mutation = useMutation({
    mutationFn: async (values: LoginFormValues) => {
      const supabase = getSupabaseBrowserClient();
      const { error } = await supabase.auth.signInWithPassword(values);
      if (error) {
        throw new Error(error.message);
      }
    },
    onSuccess: () => {
      toast.success("Hola de nuevo.");
      router.replace(nextPath);
    },
    onError: (error) => {
      toast.error(error.message);
    },
  });

  return (
    <AuthCard
      title="Iniciar sesión"
      description="Accede a tu espacio de trabajo en Mnemo."
      footerText="¿No tienes cuenta?"
      footerLinkHref="/signup"
      footerLinkLabel="Crear una"
    >
      {!configured ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Supabase no está configurado. Define `NEXT_PUBLIC_SUPABASE_URL` y
          `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
        </div>
      ) : (
        <form className="space-y-4" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
            {form.formState.errors.email && (
              <p className="text-xs text-red-600">{form.formState.errors.email.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Contraseña</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <p className="text-xs text-red-600">{form.formState.errors.password.message}</p>
            )}
          </div>

          <Button className="w-full" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Iniciando sesión…" : "Iniciar sesión"}
          </Button>
        </form>
      )}
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-4 py-8 sm:px-6">
      <div className="w-full space-y-8">
        <Link href="/" className="inline-flex text-sm font-semibold text-zinc-700 hover:text-zinc-900">
          ← Volver al inicio
        </Link>
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
