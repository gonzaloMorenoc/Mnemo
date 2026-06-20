import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyzeV2Response } from "@/lib/api/types";

interface AnalysisResultProps {
  result: AnalyzeV2Response;
}

const sourceBadgeVariant: Record<string, "org" | "user" | "global" | "default"> = {
  org: "org",
  user: "user",
  global: "global",
};

export function AnalysisResult({ result }: AnalysisResultProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Analysis Result</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <section className="space-y-1.5">
          <h3 className="text-sm font-semibold text-zinc-800">Root cause</h3>
          <p className="text-sm text-zinc-700">{result.analysis.root_cause}</p>
        </section>

        <section className="space-y-1.5">
          <h3 className="text-sm font-semibold text-zinc-800">Why it happened</h3>
          <p className="text-sm text-zinc-700">{result.analysis.why_it_happened}</p>
        </section>

        <section className="space-y-1.5">
          <h3 className="text-sm font-semibold text-zinc-800">How to fix</h3>
          <p className="text-sm text-zinc-700">{result.analysis.how_to_fix}</p>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-zinc-800">Suggested patch steps</h3>
          <ol className="space-y-1.5 pl-5 text-sm text-zinc-700">
            {result.analysis.suggested_patch_steps.map((step, index) => (
              <li key={`${index}-${step}`} className="list-decimal">
                {step}
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-zinc-800">Sources</h3>
          <div className="space-y-2">
            {result.sources.map((source, index) => (
              <div
                key={`${source.source_title}-${index}`}
                className="flex items-center justify-between rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-800">{source.source_title}</p>
                  <p className="text-xs text-zinc-500">Similarity: {source.similarity.toFixed(3)}</p>
                </div>
                <Badge variant={sourceBadgeVariant[source.scope] ?? "default"}>{source.scope}</Badge>
              </div>
            ))}
          </div>
        </section>

        <div className="flex items-center justify-between rounded-xl bg-zinc-100 px-3 py-2 text-xs text-zinc-600">
          <span>Confidence</span>
          <span className="font-semibold text-zinc-800">{(result.analysis.confidence * 100).toFixed(1)}%</span>
        </div>
      </CardContent>
    </Card>
  );
}
