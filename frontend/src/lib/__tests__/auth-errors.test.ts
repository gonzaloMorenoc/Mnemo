import { describe, expect, it } from "vitest";

import { authErrorMessage, GENERIC_AUTH_ERROR } from "@/lib/auth-errors";

describe("authErrorMessage: errores de Supabase en español", () => {
  it.each([
    [{ code: "invalid_credentials", message: "Invalid login credentials" }, /Email o contraseña incorrectos/],
    [{ code: "user_already_exists", message: "User already registered" }, /Ya existe una cuenta/],
    [{ code: "email_not_confirmed", message: "Email not confirmed" }, /confirmar tu email/],
    [{ code: "weak_password", message: "Password should be at least 6 characters" }, /contraseña es demasiado débil/],
    [{ code: "over_email_send_rate_limit", message: "rate limit" }, /Demasiados intentos/],
    [{ code: "over_request_rate_limit", message: "rate limit" }, /Demasiados intentos/],
  ])("traduce por código %o", (error, expected) => {
    expect(authErrorMessage(error)).toMatch(expected);
  });

  it("sin código, reconoce el mensaje en inglés", () => {
    expect(authErrorMessage({ message: "Invalid login credentials" })).toMatch(/Email o contraseña incorrectos/);
    expect(authErrorMessage({ message: "User already registered" })).toMatch(/Ya existe una cuenta/);
  });

  it("un fallo de red se explica como tal", () => {
    expect(authErrorMessage({ message: "Failed to fetch" })).toMatch(/conexión/);
  });

  it("lo desconocido no se pinta en inglés crudo", () => {
    expect(authErrorMessage({ message: "Something odd happened" })).toBe(GENERIC_AUTH_ERROR);
    expect(authErrorMessage(null)).toBe(GENERIC_AUTH_ERROR);
  });
});
