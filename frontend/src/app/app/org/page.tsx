"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Users } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  createOrganization,
  getOrganizations,
  joinOrganization,
} from "@/lib/api/endpoints";

const createSchema = z.object({
  name: z.string().min(2, "El nombre necesita al menos 2 caracteres."),
});

const joinSchema = z.object({
  join_code: z.string().min(4, "El código necesita al menos 4 caracteres."),
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
        throw new Error("Sesión no válida. Vuelve a iniciar sesión.");
      }
      return createOrganization(accessToken, values);
    },
    onSuccess: () => {
      toast.success("Organización creada.");
      createForm.reset();
      void queryClient.invalidateQueries({ queryKey: ["organizations", accessToken] });
    },
    onError: (error) => toast.error(error.message),
  });

  const joinMutation = useMutation({
    mutationFn: async (values: JoinFormValues) => {
      if (!accessToken) {
        throw new Error("Sesión no válida. Vuelve a iniciar sesión.");
      }
      return joinOrganization(accessToken, values);
    },
    onSuccess: () => {
      toast.success("Te has unido a la organización.");
      joinForm.reset();
      void queryClient.invalidateQueries({ queryKey: ["organizations", accessToken] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Organización</h1>
        <p className="text-sm text-zinc-500">
          Crea una organización, únete con un código e invita a tu equipo.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 size={18} />
              Crear organización
            </CardTitle>
            <CardDescription>Tu cuenta será la propietaria.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={createForm.handleSubmit((values) => createMutation.mutate(values))}>
              <div className="space-y-1.5">
                <Label htmlFor="name">Nombre de la organización</Label>
                <Input id="name" placeholder="p.ej. Acme QA" {...createForm.register("name")} />
                {createForm.formState.errors.name && (
                  <p className="text-xs text-red-600">{createForm.formState.errors.name.message}</p>
                )}
              </div>

              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creando…" : "Crear organización"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users size={18} />
              Unirse a una organización
            </CardTitle>
            <CardDescription>Usa el código de invitación de tu equipo.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={joinForm.handleSubmit((values) => joinMutation.mutate(values))}>
              <div className="space-y-1.5">
                <Label htmlFor="join_code">Código de invitación</Label>
                <Input id="join_code" placeholder="AB12CD" {...joinForm.register("join_code")} />
                {joinForm.formState.errors.join_code && (
                  <p className="text-xs text-red-600">{joinForm.formState.errors.join_code.message}</p>
                )}
              </div>

              <Button type="submit" disabled={joinMutation.isPending}>
                {joinMutation.isPending ? "Uniéndote…" : "Unirse"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Tus organizaciones</CardTitle>
          <CardDescription>Nombre, tu rol y el código para invitar a tu equipo.</CardDescription>
        </CardHeader>
        <CardContent>
          {organizationsQuery.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}

          {organizationsQuery.isError && (
            <p className="text-sm text-red-600">No se pudieron cargar las organizaciones.</p>
          )}

          {!organizationsQuery.isLoading &&
            !organizationsQuery.isError &&
            organizationsQuery.data?.length === 0 && (
              <p className="text-sm text-zinc-600">
                Aún no perteneces a ninguna organización. Crea una o únete con un código.
              </p>
            )}

          <div className="space-y-2">
            {organizationsQuery.data?.map((org) => (
              <div
                key={org.id}
                className="grid gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm md:grid-cols-[1fr_auto_auto] md:items-center"
              >
                <p className="font-medium text-zinc-800">{org.name}</p>
                <p className="text-xs text-zinc-500">Rol: {org.role ?? "member"}</p>
                <code className="rounded bg-white px-2 py-1 text-xs text-zinc-700">{org.join_code}</code>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
