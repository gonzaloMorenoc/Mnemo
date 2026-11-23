/**
 * Traduce los errores de Supabase Auth a mensajes útiles en español (F8).
 * Primero por `code` (estable), luego por el texto en inglés (versiones que no
 * mandan código) y, si no se reconoce, un mensaje genérico: nunca inglés crudo.
 */
export const GENERIC_AUTH_ERROR =
  "No se pudo completar la operación. Inténtalo de nuevo en unos segundos.";

const INVALID_CREDENTIALS = "Email o contraseña incorrectos.";
const USER_EXISTS = "Ya existe una cuenta con ese email: inicia sesión.";
const EMAIL_NOT_CONFIRMED =
  "Antes de entrar tienes que confirmar tu email: revisa tu bandeja de entrada (y la de spam).";
const WEAK_PASSWORD = "La contraseña es demasiado débil: usa al menos 6 caracteres.";
const RATE_LIMIT = "Demasiados intentos seguidos. Espera un minuto y vuelve a probar.";
const SIGNUP_DISABLED = "El registro de cuentas nuevas está desactivado ahora mismo.";
const INVALID_EMAIL = "Ese email no es válido.";
const NETWORK = "No hay conexión con el servicio de cuentas. Revisa tu conexión e inténtalo de nuevo.";

const BY_CODE: Readonly<Record<string, string>> = {
  invalid_credentials: INVALID_CREDENTIALS,
  user_already_exists: USER_EXISTS,
  email_exists: USER_EXISTS,
  email_not_confirmed: EMAIL_NOT_CONFIRMED,
  weak_password: WEAK_PASSWORD,
  over_email_send_rate_limit: RATE_LIMIT,
  over_request_rate_limit: RATE_LIMIT,
  signup_disabled: SIGNUP_DISABLED,
  email_address_invalid: INVALID_EMAIL,
};

const BY_MESSAGE: ReadonlyArray<readonly [RegExp, string]> = [
  [/invalid login credentials/i, INVALID_CREDENTIALS],
  [/already registered|already exists/i, USER_EXISTS],
  [/email not confirmed/i, EMAIL_NOT_CONFIRMED],
  [/password should be|weak password/i, WEAK_PASSWORD],
  [/rate limit|too many requests/i, RATE_LIMIT],
  [/signups? not allowed|signup is disabled/i, SIGNUP_DISABLED],
  [/failed to fetch|network|load failed/i, NETWORK],
];

export interface AuthErrorLike {
  code?: string | null;
  message?: string | null;
}

export function authErrorMessage(error: AuthErrorLike | null | undefined): string {
  if (!error) return GENERIC_AUTH_ERROR;
  const byCode = error.code ? BY_CODE[error.code] : undefined;
  if (byCode) return byCode;
  const message = error.message ?? "";
  const match = BY_MESSAGE.find(([pattern]) => pattern.test(message));
  return match ? match[1] : GENERIC_AUTH_ERROR;
}
