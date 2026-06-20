import { AlertTriangle } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface ApiGapCardProps {
  title: string;
  description: string;
  endpoint: string;
}

export function ApiGapCard({ title, description, endpoint }: ApiGapCardProps) {
  return (
    <Card className="border-amber-200 bg-amber-50/80">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-amber-900">
          <AlertTriangle size={16} />
          {title}
        </CardTitle>
        <CardDescription className="text-amber-800">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <code className="rounded-lg bg-white px-2 py-1 text-xs text-amber-900">{endpoint}</code>
      </CardContent>
    </Card>
  );
}
