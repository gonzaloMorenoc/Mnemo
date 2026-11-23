import type { UseFormRegisterReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface FormFieldProps {
  id: string;
  label: string;
  type: "email" | "password" | "text";
  autoComplete: string;
  registration: UseFormRegisterReturn;
  error?: string;
}

/** Campo con su etiqueta y su error asociado (aria-invalid + aria-describedby). */
export function FormField({ id, label, type, autoComplete, registration, error }: FormFieldProps) {
  const errorId = `${id}-error`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        autoComplete={autoComplete}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        {...registration}
      />
      {error && (
        <p id={errorId} className="text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}

/** Aviso de que faltan las variables de Supabase (configuración del despliegue). */
export function SupabaseNotConfigured() {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      El servicio de cuentas no está configurado. Define `NEXT_PUBLIC_SUPABASE_URL` y
      `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
    </div>
  );
}
