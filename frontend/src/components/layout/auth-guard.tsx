"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/providers/auth-provider";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { loading, session, configured } = useAuth();

  useEffect(() => {
    if (!loading && configured && !session) {
      const params = new URLSearchParams({ next: pathname });
      router.replace(`/login?${params.toString()}`);
    }
  }, [configured, loading, pathname, router, session]);

  if (!configured) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-xl items-center justify-center px-6">
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
          Supabase is not configured. Set `NEXT_PUBLIC_SUPABASE_URL` and
          `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
        </div>
      </div>
    );
  }

  if (loading || !session) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-xl items-center justify-center px-6">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
      </div>
    );
  }

  return <>{children}</>;
}
