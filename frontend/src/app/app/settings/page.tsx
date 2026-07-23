"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getHealth } from "@/lib/api/endpoints";

export default function SettingsPage() {
  const { user } = useAuth();

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => getHealth(),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Ajustes</h1>
        <p className="text-sm text-zinc-500">Tu cuenta y el estado de la conexión con el backend.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Cuenta</CardTitle>
          <CardDescription>Perfil básico y estado del servicio.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-zinc-700">
          <p>
            <strong>Email:</strong> {user?.email ?? "N/D"}
          </p>
          <p>
            <strong>ID de usuario:</strong> {user?.id ?? "N/D"}
          </p>

          <Separator />

          {healthQuery.isLoading && <p>Comprobando el estado del backend…</p>}
          {healthQuery.isError && (
            <p className="text-red-600">No se pudo contactar con el backend.</p>
          )}
          {healthQuery.data && (
            <div className="space-y-1">
              <p>
                <strong>Estado:</strong> {healthQuery.data.status}
              </p>
              <p>
                <strong>Modelo de IA:</strong> {healthQuery.data.model || "N/D"}
              </p>
              <p>
                <strong>Aislamiento por organización:</strong>{" "}
                {healthQuery.data.multi_tenant_enabled ? "Activado" : "Desactivado"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
