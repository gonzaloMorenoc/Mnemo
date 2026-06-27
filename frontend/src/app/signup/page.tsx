"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthCard } from "@/components/auth/auth-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

const schema = z
  .object({
    email: z.string().email("Use a valid email"),
    password: z.string().min(6, "Password must be at least 6 characters"),
    confirmPassword: z.string().min(6, "Confirm your password"),
  })
  .refine((value) => value.password === value.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match",
  });

type SignupFormValues = z.infer<typeof schema>;

export default function SignupPage() {
  const router = useRouter();
  const { configured } = useAuth();

  const form = useForm<SignupFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "",
      password: "",
      confirmPassword: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async ({ email, password }: SignupFormValues) => {
      const supabase = getSupabaseBrowserClient();
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) {
        throw new Error(error.message);
      }
      return data;
    },
    onSuccess: ({ session }) => {
      if (session) {
        toast.success("Account created.");
        router.replace("/app/assurance");
        return;
      }

      toast.success("Account created. Check your email to confirm your account.");
      router.replace("/login");
    },
    onError: (error) => {
      toast.error(error.message);
    },
  });

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-4 py-8 sm:px-6">
      <div className="w-full space-y-8">
        <Link href="/" className="inline-flex text-sm font-semibold text-zinc-700 hover:text-zinc-900">
          ← Back to home
        </Link>

        <AuthCard
          title="Create account"
          description="Start triaging incidents with TraceFix."
          footerText="Already have an account?"
          footerLinkHref="/login"
          footerLinkLabel="Sign in"
        >
          {!configured ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Supabase is not configured. Set `NEXT_PUBLIC_SUPABASE_URL` and
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
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  {...form.register("password")}
                />
                {form.formState.errors.password && (
                  <p className="text-xs text-red-600">{form.formState.errors.password.message}</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="confirmPassword">Confirm password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  {...form.register("confirmPassword")}
                />
                {form.formState.errors.confirmPassword && (
                  <p className="text-xs text-red-600">{form.formState.errors.confirmPassword.message}</p>
                )}
              </div>

              <Button className="w-full" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Creating account..." : "Create account"}
              </Button>
            </form>
          )}
        </AuthCard>
      </div>
    </main>
  );
}
