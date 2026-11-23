const env = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
};

export function getPublicEnv() {
  return env;
}

/**
 * La exportación a Xray necesita una conexión propia que todavía no se puede crear
 * desde la interfaz (hallazgo F12). Solo se ofrece si el despliegue la activa.
 * Se lee en cada llamada (Next la sustituye en build) para poder probarla.
 */
export function isXrayExportEnabled() {
  return process.env.NEXT_PUBLIC_XRAY_EXPORT_ENABLED === "true";
}

export function isSupabaseConfigured() {
  return Boolean(env.supabaseUrl && env.supabaseAnonKey);
}
