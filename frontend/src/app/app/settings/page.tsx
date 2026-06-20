"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiGapCard } from "@/components/layout/api-gap-card";
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
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Basic profile and backend connection status.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-zinc-700">
          <p>
            <strong>Email:</strong> {user?.email ?? "N/A"}
          </p>
          <p>
            <strong>User ID:</strong> {user?.id ?? "N/A"}
          </p>

          <Separator />

          {healthQuery.isLoading && <p>Checking backend health...</p>}
          {healthQuery.isError && <p className="text-red-600">Could not reach backend health endpoint.</p>}
          {healthQuery.data && (
            <div className="space-y-1">
              <p>
                <strong>Status:</strong> {healthQuery.data.status}
              </p>
              <p>
                <strong>Model:</strong> {healthQuery.data.model}
              </p>
              <p>
                <strong>Multi-tenant:</strong> {healthQuery.data.multi_tenant_enabled ? "Enabled" : "Disabled"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <ApiGapCard
        title="Analysis history is not exposed in v2 yet"
        description="Settings can include audit trails once a history endpoint is available for v2 UI."
        endpoint="Needs API (history listing for v2 UI)"
      />
    </div>
  );
}
