"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Checkbox } from "@/components/ui/checkbox";
import { ApiClientError } from "@/lib/api/client";
import { getLlmSettings, putLlmSettings } from "@/lib/api/endpoints";

const FORBIDDEN = 403;

interface Props {
  token: string;
  orgId: string;
}

/** Interruptor de LLM externo de la organización (solo owner/admin). Desactivado, las
 * funciones de IA de la org trabajan sin LLM externo (vía determinista). */
export function ExternalLlmToggle({ token, orgId }: Props) {
  const queryClient = useQueryClient();
  const queryKey = ["llm-settings", orgId];
  const settings = useQuery({
    queryKey,
    queryFn: () => getLlmSettings(token, orgId),
    retry: false,
  });
  const save = useMutation({
    mutationFn: (allow: boolean) => putLlmSettings(token, orgId, allow),
    onSuccess: (data) => queryClient.setQueryData(queryKey, data),
  });

  if (settings.isLoading) return <p>Cargando los ajustes de IA…</p>;
  if (settings.error) {
    const forbidden =
      settings.error instanceof ApiClientError && settings.error.status === FORBIDDEN;
    return (
      <p className="text-zinc-500">
        {forbidden
          ? "Solo el owner o un admin de la organización puede cambiar los ajustes de IA."
          : "No se pudieron cargar los ajustes de IA."}
      </p>
    );
  }
  if (!settings.data) return null;

  return (
    <div className="space-y-2">
      <Checkbox
        checked={settings.data.allow_external_llm}
        disabled={save.isPending}
        onChange={(event) => save.mutate(event.target.checked)}
        label="Permitir enviar datos a un LLM externo"
        hint={`Proveedor del despliegue: ${settings.data.provider}. Si lo desactivas, las funciones de IA de esta organización trabajan sin LLM externo. Lo que sale se sanea siempre (claves, tokens, DNI, IBAN, teléfonos).`}
      />
      {save.isError && <p className="text-red-600">No se pudo guardar el cambio.</p>}
    </div>
  );
}
