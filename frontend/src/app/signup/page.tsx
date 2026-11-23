"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthCard } from "@/components/auth/auth-card";
import { FormField, SupabaseNotConfigured } from "@/components/auth/form-field";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { BackendWarmup } from "@/components/warmup/BackendWarmup";
import { authErrorMessage } from "@/lib/auth-errors";
import { DEFAULT_AFTER_LOGIN } from "@/lib/safe-redirect";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

const PASSWORD_MIN = 6;

const schema = z
  .object({
    email: z.string().email("Introduce un email válido"),
    password: z.string().min(PASSWORD_MIN, `La contraseña necesita al menos ${PASSWORD_MIN} caracteres`),
    confirmPassword: z.string().min(1, "Repite la contraseña"),
  })
  .refine((value) => value.password === value.confirmPassword, {
    path: ["confirmPassword"],
    message: "Las contraseñas no coinciden",
  });

type SignupFormValues = z.infer<typeof schema>;

function ConfirmEmailNotice({ email }: { email: string }) {
  return (
    <div role="status" className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
      <p className="flex items-center gap-2 font-semibold">
        <MailCheck size={16} aria-hidden />
        Cuenta creada: confirma tu email
      </p>
      <p>
        Te hemos enviado un enlace de confirmación a <strong>{email}</strong>. Ábrelo y después
        inicia sesión. Si no lo ves en unos minutos, revisa la carpeta de spam.
      </p>
      <Button asChild size="sm" variant="outline">
        <Link href="/login">Ir a iniciar sesión</Link>
      </Button>
    </div>
  );
}

export default function SignupPage() {
  const router = useRouter();
  const { configured } = useAuth();

  const form = useForm<SignupFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", confirmPassword: "" },
  });

  const mutation = useMutation({
    mutationFn: async ({ email, password }: SignupFormValues) => {
      const supabase = getSupabaseBrowserClient();
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) {
        throw new Error(authErrorMessage(error));
      }
      return { session: data.session, email };
    },
    onSuccess: ({ session }) => {
      if (session) {
        toast.success("Cuenta creada.");
        router.replace(DEFAULT_AFTER_LOGIN);
      }
      // Sin sesión: hay que confirmar el email; el aviso se queda en pantalla.
    },
  });

  const { errors } = form.formState;
  const pendingConfirmation = mutation.isSuccess && !mutation.data.session;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-4 py-8 sm:px-6">
      <div className="w-full space-y-8">
        <Link href="/" className="inline-flex text-sm font-semibold text-zinc-700 hover:text-zinc-900">
          ← Volver al inicio
        </Link>

        <AuthCard
          title="Crear cuenta"
          description="Empieza a guardar la memoria de QA de tus proyectos con Mnemo."
          footerText="¿Ya tienes cuenta?"
          footerLinkHref="/login"
          footerLinkLabel="Iniciar sesión"
        >
          {!configured ? (
            <SupabaseNotConfigured />
          ) : pendingConfirmation ? (
            <ConfirmEmailNotice email={mutation.data.email} />
          ) : (
            <form className="space-y-4" noValidate onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
              <BackendWarmup />
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
                autoComplete="new-password"
                registration={form.register("password")}
                error={errors.password?.message}
              />
              <FormField
                id="confirmPassword"
                label="Repite la contraseña"
                type="password"
                autoComplete="new-password"
                registration={form.register("confirmPassword")}
                error={errors.confirmPassword?.message}
              />
              {mutation.isError && (
                <p role="alert" className="text-sm text-red-700">
                  {mutation.error.message}
                </p>
              )}
              <Button className="w-full" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Creando la cuenta…" : "Crear cuenta"}
              </Button>
            </form>
          )}
        </AuthCard>
      </div>
    </main>
  );
}
