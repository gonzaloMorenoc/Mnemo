"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertCircle, SearchCode } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AnalysisResult } from "@/components/analyze/analysis-result";
import { ApiGapCard } from "@/components/layout/api-gap-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { analyzeError, getOrganizations } from "@/lib/api/endpoints";

const schema = z.object({
  error_log: z.string().min(10, "Paste at least 10 characters from the error log."),
  org_id: z.string().optional(),
  top_k: z.number().min(1).max(20),
});

type AnalyzeFormValues = z.infer<typeof schema>;

export default function AnalyzePage() {
  const { accessToken } = useAuth();
  const form = useForm<AnalyzeFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      error_log: "",
      org_id: "",
      top_k: 8,
    },
  });

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });

  const analyzeMutation = useMutation({
    mutationFn: (values: AnalyzeFormValues) => {
      if (!accessToken) {
        throw new Error("Missing access token. Sign in again.");
      }

      return analyzeError(accessToken, {
        error_log: values.error_log,
        org_id: values.org_id || undefined,
        top_k: values.top_k,
      });
    },
    onSuccess: () => {
      toast.success("Analysis completed.");
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
              <SearchCode size={18} />
              Analyze Error Log
            </CardTitle>
            <CardDescription>
              Paste a raw error, pick optional org scope, and run `POST /v2/analyze`.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={form.handleSubmit((values) => analyzeMutation.mutate(values))}>
              <div className="space-y-1.5">
                <Label htmlFor="error_log">Error log</Label>
                <Textarea
                  id="error_log"
                  placeholder="Paste stack trace, exception details, and recent events..."
                  {...form.register("error_log")}
                />
                {form.formState.errors.error_log && (
                  <p className="text-xs text-red-600">{form.formState.errors.error_log.message}</p>
                )}
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="org_id">Organization scope (optional)</Label>
                  <select
                    id="org_id"
                    className="h-10 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm text-zinc-800 focus:border-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
                    {...form.register("org_id")}
                  >
                    <option value="">Personal context only</option>
                    {orgsQuery.data?.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name}
                      </option>
                    ))}
                  </select>
                  {orgsQuery.isLoading && <p className="text-xs text-zinc-500">Loading organizations...</p>}
                  {orgsQuery.isError && (
                    <p className="text-xs text-red-600">Could not load organizations.</p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="top_k">Top K context chunks (1-20)</Label>
                  <Input id="top_k" type="number" min={1} max={20} {...form.register("top_k", { valueAsNumber: true })} />
                  {form.formState.errors.top_k && (
                    <p className="text-xs text-red-600">{form.formState.errors.top_k.message}</p>
                  )}
                </div>
              </div>

              <Button type="submit" disabled={analyzeMutation.isPending}>
                {analyzeMutation.isPending ? "Analyzing..." : "Run analysis"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </motion.div>

      <Tabs defaultValue="result">
        <TabsList>
          <TabsTrigger value="result">Result</TabsTrigger>
          <TabsTrigger value="feedback-gap">Feedback API</TabsTrigger>
        </TabsList>

        <TabsContent value="result" className="space-y-4">
          {analyzeMutation.isPending && (
            <Card>
              <CardContent className="space-y-3 pt-5">
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-[90%]" />
                <Skeleton className="h-4 w-[70%]" />
              </CardContent>
            </Card>
          )}

          {analyzeMutation.isError && (
            <Card className="border-red-200 bg-red-50">
              <CardContent className="flex items-start gap-2 pt-5 text-sm text-red-800">
                <AlertCircle size={16} className="mt-0.5" />
                <span>{analyzeMutation.error.message}</span>
              </CardContent>
            </Card>
          )}

          {!analyzeMutation.data && !analyzeMutation.isPending && !analyzeMutation.isError && (
            <Card>
              <CardContent className="pt-5 text-sm text-zinc-600">
                No analysis yet. Paste an error log and click <strong>Run analysis</strong>.
              </CardContent>
            </Card>
          )}

          {analyzeMutation.data && <AnalysisResult result={analyzeMutation.data} />}
        </TabsContent>

        <TabsContent value="feedback-gap">
          <ApiGapCard
            title="Feedback submission requires new API"
            description="The backend does not expose helpful/not-helpful feedback for analysis yet."
            endpoint="POST /v2/analyses/:id/feedback"
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
