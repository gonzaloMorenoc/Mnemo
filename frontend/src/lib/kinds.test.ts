import { describe, expect, it } from "vitest";

import {
  KIND_HINT,
  KIND_LABEL,
  KIND_OPTIONS,
  KIND_ORDER,
  kindLabel,
  looksLikePersonalEmail,
} from "./kinds";

describe("kinds", () => {
  it("tiene los 11 tipos del esquema", () => {
    expect(KIND_ORDER).toHaveLength(11);
  });

  it("incluye los kinds operativos del oficio", () => {
    expect(KIND_ORDER).toEqual(
      expect.arrayContaining(["runbook", "dato_prueba", "contacto", "decision"]),
    );
  });

  it("da etiqueta en español a todos", () => {
    for (const kind of KIND_ORDER) {
      expect(KIND_LABEL[kind]).toBeTruthy();
    }
  });

  it("KIND_OPTIONS sigue el orden de KIND_ORDER", () => {
    expect(KIND_OPTIONS.map((o) => o.value)).toEqual([...KIND_ORDER]);
  });

  it("kindLabel traduce los conocidos", () => {
    expect(kindLabel("runbook")).toBe("Runbook");
  });

  it("kindLabel devuelve el valor crudo si no lo conoce", () => {
    // El backend podría desplegarse antes que el frontend: mejor mostrar el kind
    // tal cual que un "undefined" en pantalla.
    expect(kindLabel("kind_del_futuro")).toBe("kind_del_futuro");
  });
});

describe("guía de contacto", () => {
  it("da pista de redacción a los kinds del oficio", () => {
    expect(KIND_HINT.contacto).toBeTruthy();
    expect(KIND_HINT.runbook).toBeTruthy();
  });

  it("detecta un email para avisar", () => {
    expect(looksLikePersonalEmail("pregunta a laura.gomez@empresa.com")).toBe(true);
  });

  it("no avisa cuando no hay email", () => {
    expect(looksLikePersonalEmail("lo lleva el equipo de Pagos, canal #pagos")).toBe(false);
  });
});
