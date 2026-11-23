"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Users, type LucideIcon } from "lucide-react";
import { useId } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createOrganization, joinOrganization } from "@/lib/api/endpoints";
import type { OrganizationResponse } from "@/lib/api/types";

const NAME_MIN = 2;
const NAME_MAX = 80;
const CODE_MIN = 4;
const SESSION_EXPIRED = "Sesión no válida. Vuelve a iniciar sesión.";

const createSchema = z.object({
  value: z
    .string()
    .trim()
    .min(NAME_MIN, `El nombre necesita al menos ${NAME_MIN} caracteres.`)
    .max(NAME_MAX, `El nombre admite como mucho ${NAME_MAX} caracteres.`),
});
const joinSchema = z.object({
  value: z.string().trim().min(CODE_MIN, `El código necesita al menos ${CODE_MIN} caracteres.`),
});
type FormValues = z.infer<typeof createSchema>;

interface OrgActionCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  label: string;
  placeholder: string;
  submitLabel: string;
  pendingLabel: string;
  schema: typeof createSchema;
  successMessage: string;
  submit: (token: string, value: string) => Promise<OrganizationResponse>;
}

/** Una tarjeta con un único campo que crea o une a una organización y la activa. */
function OrgActionCard(props: OrgActionCardProps) {
  const { accessToken } = useAuth();
  const { setActiveOrgId } = useActiveOrg();
  const queryClient = useQueryClient();
  const fieldId = useId();
  const errorId = `${fieldId}-error`;
  const form = useForm<FormValues>({ resolver: zodResolver(props.schema), defaultValues: { value: "" } });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      if (!accessToken) return Promise.reject(new Error(SESSION_EXPIRED));
      return props.submit(accessToken, values.value);
    },
    onSuccess: (org) => {
      toast.success(props.successMessage);
      setActiveOrgId(org.id);
      void queryClient.invalidateQueries({ queryKey: ["organizations", accessToken] });
    },
  });

  const fieldError = form.formState.errors.value?.message;
  const errorText = fieldError ?? (mutation.isError ? mutation.error.message : null);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <props.icon size={18} aria-hidden />
          {props.title}
        </CardTitle>
        <CardDescription>{props.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" noValidate onSubmit={form.handleSubmit((v) => mutation.mutate(v))}>
          <div className="space-y-1.5">
            <Label htmlFor={fieldId}>{props.label}</Label>
            <Input
              id={fieldId}
              placeholder={props.placeholder}
              aria-invalid={Boolean(errorText)}
              aria-describedby={errorText ? errorId : undefined}
              {...form.register("value")}
            />
            {errorText && (
              <p id={errorId} role="alert" className="text-xs text-red-600">
                {errorText}
              </p>
            )}
          </div>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? props.pendingLabel : props.submitLabel}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/**
 * Estado «sin organización» compartido por toda la app (hallazgo #15/F1): en vez de
 * un «Selecciona una organización.» sin botón, dos salidas reales en el sitio.
 */
export function NoOrgState() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Bienvenido a Mnemo</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Para empezar necesitas un espacio de trabajo: la organización de tu consultora o de tu
          equipo de QA. Ahí vivirán tus proyectos, sus ejecuciones y lo que el equipo sabe de
          ellos.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <OrgActionCard
          icon={Building2}
          title="Crear organización"
          description="Tu cuenta será la propietaria y podrás invitar al equipo."
          label="Nombre de tu organización"
          placeholder="p. ej. QA de Acme"
          submitLabel="Crear organización"
          pendingLabel="Creando…"
          schema={createSchema}
          successMessage="Organización creada."
          submit={(token, name) => createOrganization(token, { name })}
        />
        <OrgActionCard
          icon={Users}
          title="Unirme a la de mi equipo"
          description="Pide el código de invitación a quien administre la organización."
          label="Código de invitación"
          placeholder="AB12CD"
          submitLabel="Unirme con un código"
          pendingLabel="Uniéndote…"
          schema={joinSchema}
          successMessage="Te has unido a la organización."
          submit={(token, join_code) => joinOrganization(token, { join_code })}
        />
      </div>
    </div>
  );
}
