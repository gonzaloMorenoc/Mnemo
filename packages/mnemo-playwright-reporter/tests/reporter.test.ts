import { describe, it, expect, vi, afterEach } from "vitest";
import { MnemoReporter, parseErrorType, toTestResultInput } from "../src/reporter";

const tcase = (over = {}) => ({
  titlePath: () => ["suite", "name"],
  location: { file: "a.spec.ts", line: 10 },
  ...over,
});

describe("parseErrorType", () => {
  it("extrae el primer token XxxError/Exception", () => {
    expect(parseErrorType("TimeoutError: locator not found")).toBe("TimeoutError");
  });
  it("devuelve null si no hay token o no hay mensaje", () => {
    expect(parseErrorType("algo salió mal")).toBeNull();
    expect(parseErrorType(null)).toBeNull();
  });
});

describe("toTestResultInput", () => {
  it("mapea estados passed/failed/timedOut/skipped", () => {
    expect(toTestResultInput(tcase() as any, { status: "passed", retry: 0 } as any).status).toBe("pass");
    expect(toTestResultInput(tcase() as any, { status: "failed", retry: 0 } as any).status).toBe("fail");
    expect(toTestResultInput(tcase() as any, { status: "timedOut", retry: 0 } as any).status).toBe("fail");
    expect(toTestResultInput(tcase() as any, { status: "skipped", retry: 0 } as any).status).toBe("skipped");
  });
  it("passed con retry>0 -> flaky + retried", () => {
    const r = toTestResultInput(tcase() as any, { status: "passed", retry: 1 } as any);
    expect(r.status).toBe("flaky");
    expect(r.retried).toBe(true);
  });
  it("extrae error_type/message/file/line y el dom del attachment", () => {
    const r = toTestResultInput(tcase() as any, {
      status: "failed",
      retry: 0,
      error: { message: "AssertionError: nope", stack: "at a.spec.ts:10" },
      attachments: [{ name: "mnemo-dom", body: Buffer.from("<html></html>"), contentType: "text/html" }],
    } as any);
    expect(r.errorType).toBe("AssertionError");
    expect(r.message).toBe("AssertionError: nope");
    expect(r.trace).toBe("at a.spec.ts:10");
    expect(r.file).toBe("a.spec.ts");
    expect(r.line).toBe(10);
    expect(r.dom).toBe("<html></html>");
  });
});

describe("MnemoReporter", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("dedup por reintentos: conserva el intento final (flaky) y POSTea una vez", async () => {
    const reporter = new MnemoReporter({
      url: "http://x/v2/ci/webhook", secret: "s", orgId: "o", project: "p", commitSha: "abc",
    });
    const tc: any = { id: "t1", titlePath: () => ["login"], location: { file: "l.ts", line: 1 } };
    reporter.onTestEnd(tc, { status: "failed", retry: 0 } as any);
    reporter.onTestEnd(tc, { status: "passed", retry: 1 } as any);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);
    await reporter.onEnd();
    expect(fetchMock).toHaveBeenCalledOnce();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.tests).toHaveLength(1);
    expect(body.tests[0].status).toBe("flaky");
    expect(body.tests[0].retried).toBe(true);
  });

  it("no-opera (sin POST) si la config está incompleta", async () => {
    const reporter = new MnemoReporter({}); // sin opciones; el env de test no tiene MNEMO_*
    const tc: any = { id: "t1", titlePath: () => ["x"], location: {} };
    reporter.onTestEnd(tc, { status: "passed", retry: 0 } as any);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await reporter.onEnd();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
