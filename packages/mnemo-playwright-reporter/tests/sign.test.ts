import { describe, it, expect } from "vitest";
import { sign } from "../src/sign";

describe("sign", () => {
  it("produce el mismo HMAC que el backend Python (interop)", () => {
    const body =
      '{"project":"demo","org_id":"org-1","commit_sha":"abc123","source":"playwright","tests":[]}';
    // Valor fijado con hmac.new(secret, body, sha256).hexdigest() en Python.
    expect(sign(body, "mnemo-test-secret")).toBe(
      "sha256=5eff407fdd992b247c9e7107e4ee38873454f47717311dab75f7e2f748377a88",
    );
  });

  it("cambia si cambia el cuerpo", () => {
    expect(sign("a", "k")).not.toBe(sign("b", "k"));
  });
});
