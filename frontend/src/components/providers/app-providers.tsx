"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { MotionConfig } from "framer-motion";
import { Toaster } from "sonner";

import { AuthProvider } from "@/components/providers/auth-provider";
import { queryRetryDelay, shouldRetryQuery } from "@/lib/api/retry";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 20_000,
            refetchOnWindowFocus: false,
            // 502/504 y red caída = backend despertando: varios reintentos con
            // espera creciente; un 4xx no se reintenta (ver lib/api/retry.ts).
            retry: shouldRetryQuery,
            retryDelay: queryRetryDelay,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {/* reducedMotion="user": quien pide menos movimiento al sistema no ve las
            transiciones de framer-motion. Toasts abajo: arriba tapaban la cabecera. */}
        <MotionConfig reducedMotion="user">{children}</MotionConfig>
        <Toaster richColors position="bottom-right" />
      </AuthProvider>
    </QueryClientProvider>
  );
}
