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
import { FormField, SupabaseNotConfigured } from "@/components/auth/form-field";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { BackendWarmup } from "@/components/warmup/BackendWarmup";
import { authErrorMessage } from "@/lib/auth-errors";
import { safeNextPath } from "@/lib/safe-redirect";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

const PASSWORD_MIN = 6;

const schema = z.object({
  email: z.string().email("Introduce un email válido"),
  password: z.string().min(PASSWORD_MIN, `La contraseña necesita al menos ${PASSWORD_MIN} caracteres`),
});

type LoginFormValues = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { session, configured } = useAuth();
  // Solo rutas internas: un ?next=https://… o //… sería una redirección abierta (#16).
  const nextPath = safeNextPath(searchParams.get("next"));

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
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
        throw new Error(authErrorMessage(error));
      }
    },
    onSuccess: () => {
      toast.success("Hola de nuevo.");
      router.replace(nextPath);
    },
  });

  const { errors } = form.formState;

  return (
    <AuthCard
      title="Iniciar sesión"
      description="Mnemo guarda la memoria de QA de tus proyectos para que no se pierda cuando alguien rota."
      footerText="¿No tienes cuenta?"
      footerLinkHref="/signup"
      footerLinkLabel="Crear una"
    >
      {!configured ? (
        <SupabaseNotConfigured />
      ) : (
        <form className="space-y-4" noValidate onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <BackendWarmup showNotice />
          <FormField
            id="email"
            label="Email"
            type="email"
            autoComplete="email"
            registration={form.register("email")}
            error={errors.email?.message}
          />
          <FormField
            id="password"
            label="Contraseña"
            type="password"
            autoComplete="current-password"
            registration={form.register("password")}
            error={errors.password?.message}
          />
          {mutation.isError && (
            <p role="alert" className="text-sm text-red-700">
              {mutation.error.message}
            </p>
          )}
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
