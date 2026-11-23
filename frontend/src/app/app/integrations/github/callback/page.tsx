"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { GithubCallbackView } from "@/components/integrations/GithubCallbackView";

// Callback de la GitHub App (configurar como «Callback URL» en la App):
// GitHub vuelve aquí con installation_id, code, state y setup_action.
function CallbackFromQuery() {
  const query = useSearchParams();
  const params = {
    installationId: query.get("installation_id") ?? "",
    code: query.get("code") ?? "",
    state: query.get("state") ?? "",
    setupAction: query.get("setup_action") ?? "",
  };
  return <GithubCallbackView params={params} />;
}

export default function GithubCallbackPage() {
  // useSearchParams exige un límite de Suspense en el App Router.
  return (
    <Suspense fallback={null}>
      <CallbackFromQuery />
    </Suspense>
  );
}
