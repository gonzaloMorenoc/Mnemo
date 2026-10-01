"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { MotionConfig } from "framer-motion";
import { Toaster } from "sonner";

import { AuthProvider } from "@/components/providers/auth-provider";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 20_000,
            refetchOnWindowFocus: false,
            retry: 1,
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
