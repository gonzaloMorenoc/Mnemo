"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { setFamilyLabel } from "@/lib/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const LABELS = ["unknown", "flaky", "real", "maintenance", "infra"];

export function FamilyLabelControl({ familyId }: { familyId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [label, setLabel] = useState("unknown");
  const [reason, setReason] = useState("");

  const mut = useMutation({
    mutationFn: () => setFamilyLabel(accessToken!, familyId, label, reason),
    onSuccess: () => {
      toast.success("Familia etiquetada.");
      qc.invalidateQueries({ queryKey: ["lineage", familyId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3">
      <p className="text-xs font-medium text-zinc-500">Calibrar (etiqueta esta familia)</p>
      <div className="space-y-1">
        <Label htmlFor="cat">Categoría</Label>
        <select
          id="cat"
          className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        >
          {LABELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
      <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="motivo (opcional)" />
      <Button className="text-xs" disabled={mut.isPending} onClick={() => mut.mutate()}>
        {mut.isPending ? "Guardando…" : "Etiquetar familia"}
      </Button>
    </div>
  );
}
