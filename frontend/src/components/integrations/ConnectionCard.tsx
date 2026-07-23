"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Tarjeta de conexión colapsable para Integraciones. Colapsada por defecto con un
 * pill de estado en la cabecera → se ve de un vistazo qué está conectado sin scroll.
 * Las acciones de cada conexión (indexar, importar) van anidadas dentro.
 */
export function ConnectionCard({
  title,
  icon,
  connected,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  connected?: boolean; // undefined = sin pill de estado
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="max-w-xl overflow-hidden p-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 px-5 py-4 text-left transition-colors hover:bg-zinc-50"
      >
        <span className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-medium text-zinc-900">{title}</span>
          {connected !== undefined &&
            (connected ? (
              <Badge className="border-emerald-200 bg-emerald-100 text-emerald-800">
                ✓ Conectado
              </Badge>
            ) : (
              <Badge className="border-zinc-200 bg-zinc-50 text-zinc-500">Sin configurar</Badge>
            ))}
        </span>
        <ChevronDown
          size={16}
          className={cn("shrink-0 text-zinc-400 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && <div className="space-y-4 border-t border-zinc-100 px-5 py-5">{children}</div>}
    </Card>
  );
}
