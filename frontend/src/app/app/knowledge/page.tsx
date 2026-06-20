"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FileUp } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ApiGapCard } from "@/components/layout/api-gap-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getOrganizations, uploadKnowledge } from "@/lib/api/endpoints";

const schema = z
  .object({
    scope: z.enum(["user", "org"]),
    org_id: z.string().optional(),
    contribute_global: z.boolean(),
  })
  .superRefine((value, ctx) => {
    if (value.scope === "org" && !value.org_id) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["org_id"],
        message: "Choose an organization for org scope uploads.",
      });
    }
  });

type KnowledgeFormValues = z.infer<typeof schema>;

export default function KnowledgePage() {
  const { accessToken } = useAuth();
  const [file, setFile] = useState<File | null>(null);

  const form = useForm<KnowledgeFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      scope: "user",
      org_id: "",
      contribute_global: false,
    },
  });

  // eslint-disable-next-line react-hooks/incompatible-library
  const scope = form.watch("scope");

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });

  const uploadMutation = useMutation({
    mutationFn: async (values: KnowledgeFormValues) => {
      if (!accessToken) {
        throw new Error("Missing access token. Sign in again.");
      }
      if (!file) {
        throw new Error("Select a file to upload.");
      }

      const formData = new FormData();
      formData.append("file", file);
      formData.append("scope", values.scope);
      if (values.org_id) {
        formData.append("org_id", values.org_id);
      }
      formData.append("contribute_global", String(values.contribute_global));

      return uploadKnowledge(accessToken, formData);
    },
    onSuccess: () => {
      toast.success("Document uploaded and ingested.");
    },
    onError: (error) => {
      toast.error(error.message);
    },
  });

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileUp size={18} />
              Upload Knowledge
            </CardTitle>
            <CardDescription>
              Upload docs or logs via `POST /v2/upload` to user or organization scope.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={form.handleSubmit((values) => uploadMutation.mutate(values))}>
              <div className="space-y-1.5">
                <Label htmlFor="file">File</Label>
                <input
                  id="file"
                  type="file"
                  className="block w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-700 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-900 file:px-3 file:py-1.5 file:text-white"
                  onChange={(event) => {
                    const selected = event.target.files?.[0] ?? null;
                    setFile(selected);
                  }}
                />
                {!file && <p className="text-xs text-zinc-500">Supported: .log, .txt, .md, .pdf, .json.</p>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="scope">Scope</Label>
                <select
                  id="scope"
                  className="h-10 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm text-zinc-800 focus:border-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
                  {...form.register("scope")}
                >
                  <option value="user">User</option>
                  <option value="org">Organization</option>
                </select>
              </div>

              {scope === "org" && (
                <div className="space-y-1.5">
                  <Label htmlFor="org_id">Organization</Label>
                  <select
                    id="org_id"
                    className="h-10 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm text-zinc-800 focus:border-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
                    {...form.register("org_id")}
                  >
                    <option value="">Select organization</option>
                    {orgsQuery.data?.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name}
                      </option>
                    ))}
                  </select>
                  {form.formState.errors.org_id && (
                    <p className="text-xs text-red-600">{form.formState.errors.org_id.message}</p>
                  )}
                </div>
              )}

              <Checkbox
                checked={form.watch("contribute_global")}
                onChange={(event) => form.setValue("contribute_global", event.currentTarget.checked)}
                label="Contribute to global pool"
                hint="Also contributes chunks to global knowledge when true."
              />

              <Button type="submit" disabled={uploadMutation.isPending}>
                {uploadMutation.isPending ? "Uploading..." : "Upload file"}
              </Button>
            </form>

            {uploadMutation.data && (
              <div className="mt-5 space-y-2 rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700">
                <p>
                  <strong>Document ID:</strong> {uploadMutation.data.document_id}
                </p>
                <p>
                  <strong>Global document ID:</strong> {uploadMutation.data.global_document_id ?? "N/A"}
                </p>
                <p>
                  <strong>Chunks:</strong> {uploadMutation.data.chunk_count}
                </p>
                <p>
                  <strong>Storage path:</strong> {uploadMutation.data.storage_path}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      <Tabs defaultValue="documents-gap">
        <TabsList>
          <TabsTrigger value="documents-gap">Documents API gap</TabsTrigger>
          <TabsTrigger value="delete-gap">Delete API gap</TabsTrigger>
        </TabsList>

        <TabsContent value="documents-gap">
          <ApiGapCard
            title="Document listing is not available yet"
            description="The UI is ready for a list view, but backend endpoint is missing."
            endpoint="GET /v2/knowledge/documents?scope=&org_id="
          />
        </TabsContent>

        <TabsContent value="delete-gap">
          <ApiGapCard
            title="Document deletion is not available yet"
            description="Delete actions are intentionally disabled until backend contract exists."
            endpoint="DELETE /v2/knowledge/documents/:id"
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
