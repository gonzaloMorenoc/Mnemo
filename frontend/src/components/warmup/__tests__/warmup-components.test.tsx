// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/warmup", () => ({
  WAKING_NOTICE_AFTER_MS: 3000,
  warmBackend: vi.fn(),
}));

import { ApiClientError } from "@/lib/api/client";
import { warmBackend } from "@/lib/warmup";
import { BackendWarmup } from "@/components/warmup/BackendWarmup";
import { hasWakingQueries, ServerWakingBanner } from "@/components/warmup/ServerWakingBanner";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("BackendWarmup", () => {
  it("lanza el ping al montar y no pinta nada si responde rápido", async () => {
    vi.mocked(warmBackend).mockResolvedValue("ready");
    const { container } = render(<BackendWarmup showNotice />);
    expect(warmBackend).toHaveBeenCalled();
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
  });

  it("si tarda, avisa de que el servidor está despertando (no un error)", async () => {
    vi.useFakeTimers();
    vi.mocked(warmBackend).mockReturnValue(new Promise(() => {}));
    render(<BackendWarmup showNotice />);
    await act(async () => {
      vi.advanceTimersByTime(3500);
    });
    expect(screen.getByRole("status")).toHaveTextContent(/Despertando el servidor/);
  });

  it("si no despierta, lo dice con calma", async () => {
    vi.mocked(warmBackend).mockResolvedValue("unreachable");
    render(<BackendWarmup showNotice />);
    expect(await screen.findByRole("status")).toHaveTextContent(/aún no responde/);
  });
});

describe("ServerWakingBanner", () => {
  it("detecta consultas reintentando tras un 504", () => {
    const client = new QueryClient();
    const cache = client.getQueryCache();
    expect(hasWakingQueries(cache)).toBe(false);
    const query = cache.build(client, { queryKey: ["x"] });
    query.setState({
      ...query.state,
      fetchStatus: "fetching",
      fetchFailureCount: 1,
      fetchFailureReason: new ApiClientError("x", 504),
    });
    expect(hasWakingQueries(cache)).toBe(true);
    query.setState({ ...query.state, fetchFailureReason: new ApiClientError("x", 404) });
    expect(hasWakingQueries(cache)).toBe(false);
  });

  it("no pinta nada sin consultas despertando", () => {
    const client = new QueryClient();
    const { container } = render(
      <QueryClientProvider client={client}>
        <ServerWakingBanner />
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
