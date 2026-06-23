import { sign } from "./sign";
import { CiRunArtifact, MnemoConfig } from "./types";

type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; body: string },
) => Promise<{ ok: boolean; status: number }>;

/** Firma y envía el artefacto. Failure-safe: nunca lanza (un reporter no debe tumbar el CI). */
export async function postArtifact(
  config: MnemoConfig,
  artifact: CiRunArtifact,
  fetchImpl: FetchLike = fetch as unknown as FetchLike,
): Promise<void> {
  try {
    const body = JSON.stringify(artifact);
    const signature = sign(body, config.secret);
    const res = await fetchImpl(config.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hub-Signature-256": signature },
      body,
    });
    if (!res.ok) {
      console.warn(`[mnemo] webhook respondió ${res.status}; artefacto no ingerido`);
    }
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    console.warn(`[mnemo] no se pudo enviar el artefacto: ${reason}`);
  }
}
