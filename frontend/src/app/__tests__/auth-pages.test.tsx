// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
let search = "";
const auth = { session: null as unknown, configured: true };
const signInWithPassword = vi.fn();
const signUp = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => auth }));
vi.mock("@/lib/supabase/client", () => ({
  getSupabaseBrowserClient: () => ({ auth: { signInWithPassword, signUp } }),
}));
vi.mock("@/lib/warmup", () => ({ WAKING_NOTICE_AFTER_MS: 3000, warmBackend: vi.fn(() => new Promise(() => {})) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { warmBackend } from "@/lib/warmup";
import LoginPage from "@/app/login/page";
import SignupPage from "@/app/signup/page";

function renderPage(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function fillLogin() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ana@example.com" } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "secreto123" } });
  fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));
}

beforeEach(() => {
  search = "";
  auth.session = null;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Login", () => {
  it("calienta el backend al cargar", () => {
    renderPage(<LoginPage />);
    expect(warmBackend).toHaveBeenCalled();
  });

  it("tras entrar va a la ruta interna de ?next=", async () => {
    search = "next=/app/knowledge";
    signInWithPassword.mockResolvedValue({ error: null });
    renderPage(<LoginPage />);
    fillLogin();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/knowledge"));
  });

  it.each(["https://phishing.example", "//phishing.example", "/\\phishing.example"])(
    "ignora un ?next= externo (%s) y va a Continuidad",
    async (next) => {
      search = `next=${encodeURIComponent(next)}`;
      signInWithPassword.mockResolvedValue({ error: null });
      renderPage(<LoginPage />);
      fillLogin();
      await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/continuity"));
      expect(replace).not.toHaveBeenCalledWith(next);
    },
  );

  it("con sesión abierta no salta a un ?next= externo", () => {
    search = "next=https://phishing.example";
    auth.session = { access_token: "t" };
    renderPage(<LoginPage />);
    expect(replace).toHaveBeenCalledWith("/app/continuity");
  });

  it("traduce el error de credenciales de Supabase", async () => {
    signInWithPassword.mockResolvedValue({
      error: { code: "invalid_credentials", message: "Invalid login credentials" },
    });
    renderPage(<LoginPage />);
    fillLogin();
    expect(await screen.findByRole("alert")).toHaveTextContent("Email o contraseña incorrectos.");
  });
});

describe("Registro", () => {
  function fillSignup(confirm = "secreto123") {
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ana@example.com" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "secreto123" } });
    fireEvent.change(screen.getByLabelText("Repite la contraseña"), { target: { value: confirm } });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
  }

  it("está entero en español", () => {
    renderPage(<SignupPage />);
    expect(screen.getByText("← Volver al inicio")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
    expect(screen.queryByText(/Create account|Back to home|Confirm password/)).not.toBeInTheDocument();
  });

  it("valida en español que las contraseñas coincidan", async () => {
    renderPage(<SignupPage />);
    fillSignup("otra-cosa");
    expect(await screen.findByText("Las contraseñas no coinciden")).toBeInTheDocument();
    expect(signUp).not.toHaveBeenCalled();
  });

  it("sin sesión (confirmación por email) lo explica en pantalla", async () => {
    signUp.mockResolvedValue({ data: { session: null }, error: null });
    renderPage(<SignupPage />);
    fillSignup();
    expect(await screen.findByRole("status")).toHaveTextContent(/confirma tu email/i);
    expect(screen.getByText("ana@example.com")).toBeInTheDocument();
  });

  it("con sesión va directo a la app", async () => {
    signUp.mockResolvedValue({ data: { session: { access_token: "t" } }, error: null });
    renderPage(<SignupPage />);
    fillSignup();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/continuity"));
  });

  it("traduce «usuario ya registrado»", async () => {
    signUp.mockResolvedValue({ data: {}, error: { message: "User already registered" } });
    renderPage(<SignupPage />);
    fillSignup();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Ya existe una cuenta/);
  });
});
