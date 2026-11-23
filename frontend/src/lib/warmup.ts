/**
 * Calentamiento del backend (hallazgo F5). El backend gratuito se duerme y tarda
 * ~1 minuto en arrancar: lanzar un ping ligero al cargar la landing o el login
 * hace que despierte mientras la persona escribe la contraseña.
 */
export const HEALTH_PATH = "/api/health";
/** A partir de aquí sin respuesta, se avisa de que el servidor está despertando. */
export const WAKING_NOTICE_AFTER_MS = 3_000;
const DEFAULT_ATTEMPTS = 3;
const DEFAULT_RETRY_DELAY_MS = 3_000;

export type WarmupResult = "ready" | "unreachable";

interface PingOptions {
  attempts?: number;
  retryDelayMs?: number;
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

async function pingOnce(): Promise<boolean> {
  try {
    const res = await fetch(HEALTH_PATH, { method: "GET", cache: "no-store" });
    return res.ok;
  } catch {
    // Red caída o proxy sin respuesta: es justo lo que se reintenta.
    return false;
  }
}

export async function pingBackend(options: PingOptions = {}): Promise<WarmupResult> {
  const attempts = options.attempts ?? DEFAULT_ATTEMPTS;
  const retryDelayMs = options.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await pingOnce()) return "ready";
    if (attempt < attempts - 1) await wait(retryDelayMs);
  }
  return "unreachable";
}

let inflight: Promise<WarmupResult> | null = null;

/** Un único ping por carga de página, compartido por quien lo pida. */
export function warmBackend(): Promise<WarmupResult> {
  if (!inflight) inflight = pingBackend();
  return inflight;
}

export function resetWarmupForTests(): void {
  inflight = null;
}
