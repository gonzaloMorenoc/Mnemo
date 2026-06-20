"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Users } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ApiGapCard } from "@/components/layout/api-gap-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  createOrganization,
  getOrganizations,
  joinOrganization,
} from "@/lib/api/endpoints";

const createSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters."),
});

const joinSchema = z.object({
  join_code: z.string().min(4, "Join code must be at least 4 characters."),
});

type CreateFormValues = z.infer<typeof createSchema>;
type JoinFormValues = z.infer<typeof joinSchema>;

export default function OrganizationPage() {
  const queryClient = useQueryClient();
  const { accessToken } = useAuth();

  const organizationsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });

  const createForm = useForm<CreateFormValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { name: "" },
  });

  const joinForm = useForm<JoinFormValues>({
    resolver: zodResolver(joinSchema),
    defaultValues: { join_code: "" },
  });

  const createMutation = useMutation({
    mutationFn: async (values: CreateFormValues) => {
      if (!accessToken) {
        throw new Error("Missing access token.");
      }
      return createOrganization(accessToken, values);
    },
    onSuccess: () => {
      toast.success("Organization created.");
      createForm.reset();
      void queryClient.invalidateQueries({ queryKey: ["organizations", accessToken] });
    },
    onError: (error) => toast.error(error.message),
  });

  const joinMutation = useMutation({
    mutationFn: async (values: JoinFormValues) => {
      if (!accessToken) {
        throw new Error("Missing access token.");
      }
      return joinOrganization(accessToken, values);
    },
    onSuccess: () => {
      toast.success("Joined organization.");
      joinForm.reset();
      void queryClient.invalidateQueries({ queryKey: ["organizations", accessToken] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 size={18} />
              Create organization
            </CardTitle>
            <CardDescription>Create a new organization with your account as owner.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={createForm.handleSubmit((values) => createMutation.mutate(values))}>
              <div className="space-y-1.5">
                <Label htmlFor="name">Organization name</Label>
                <Input id="name" placeholder="Acme Reliability" {...createForm.register("name")} />
                {createForm.formState.errors.name && (
                  <p className="text-xs text-red-600">{createForm.formState.errors.name.message}</p>
                )}
              </div>

              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create org"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users size={18} />
              Join organization
            </CardTitle>
            <CardDescription>Join an existing org using its join code.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={joinForm.handleSubmit((values) => joinMutation.mutate(values))}>
              <div className="space-y-1.5">
                <Label htmlFor="join_code">Join code</Label>
                <Input id="join_code" placeholder="AB12CD" {...joinForm.register("join_code")} />
                {joinForm.formState.errors.join_code && (
                  <p className="text-xs text-red-600">{joinForm.formState.errors.join_code.message}</p>
                )}
              </div>

              <Button type="submit" disabled={joinMutation.isPending}>
                {joinMutation.isPending ? "Joining..." : "Join org"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your organizations</CardTitle>
          <CardDescription>Loaded from `GET /v2/orgs`.</CardDescription>
        </CardHeader>
        <CardContent>
          {organizationsQuery.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}

          {organizationsQuery.isError && (
            <p className="text-sm text-red-600">Could not fetch organizations.</p>
          )}

          {!organizationsQuery.isLoading &&
            !organizationsQuery.isError &&
            organizationsQuery.data?.length === 0 && (
              <p className="text-sm text-zinc-600">No organizations yet. Create one or join using a code.</p>
            )}

          <div className="space-y-2">
            {organizationsQuery.data?.map((org) => (
              <div
                key={org.id}
                className="grid gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm md:grid-cols-[1fr_auto_auto] md:items-center"
              >
                <p className="font-medium text-zinc-800">{org.name}</p>
                <p className="text-xs text-zinc-500">Role: {org.role ?? "member"}</p>
                <code className="rounded bg-white px-2 py-1 text-xs text-zinc-700">{org.join_code}</code>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="members-gap">
        <TabsList>
          <TabsTrigger value="members-gap">Members API gap</TabsTrigger>
          <TabsTrigger value="roles-gap">Roles API gap</TabsTrigger>
        </TabsList>

        <TabsContent value="members-gap">
          <ApiGapCard
            title="Organization members list requires backend support"
            description="Member directory UI will be enabled after this endpoint is available."
            endpoint="GET /v2/orgs/:org_id/members"
          />
        </TabsContent>

        <TabsContent value="roles-gap">
          <ApiGapCard
            title="Role updates require backend support"
            description="Role management actions are disabled until API is implemented."
            endpoint="PATCH /v2/orgs/:org_id/members/:user_id"
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
