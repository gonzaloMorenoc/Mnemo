import type { Metadata } from "next";

import { AuthGuard } from "@/components/layout/auth-guard";
import { AppShell } from "@/components/layout/app-shell";

// Título del Panel de control (/app); cada sección define el suyo en su layout.
export const metadata: Metadata = { title: "Panel de control" };

export default function AuthenticatedAppLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
