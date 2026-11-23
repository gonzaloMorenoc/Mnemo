// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FileDropzone } from "@/components/ui/file-dropzone";
import { MAX_UPLOAD_BYTES } from "@/lib/upload-limits";

afterEach(cleanup);

describe("FileDropzone", () => {
  it("muestra la invitación y el hint cuando no hay archivo", () => {
    render(<FileDropzone file={null} onFile={vi.fn()} hint="JUnit, Allure…" />);
    expect(screen.getByText(/Arrastra el archivo aquí/i)).toBeInTheDocument();
    expect(screen.getByText("JUnit, Allure…")).toBeInTheDocument();
  });

  it("acepta un archivo por drop", () => {
    const onFile = vi.fn();
    render(<FileDropzone file={null} onFile={onFile} />);
    const f = new File(["<xml/>"], "junit.xml", { type: "application/xml" });
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [f] } });
    expect(onFile).toHaveBeenCalledWith(f);
  });

  it("muestra el nombre del archivo y permite quitarlo", () => {
    const onFile = vi.fn();
    const f = new File(["x"], "resultados.xml", { type: "application/xml" });
    render(<FileDropzone file={f} onFile={onFile} />);
    expect(screen.getByText("resultados.xml")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Quitar archivo/i }));
    expect(onFile).toHaveBeenCalledWith(null);
  });

  it("rechaza en el cliente un archivo que supera el límite de subida, con un mensaje claro", () => {
    const onFile = vi.fn();
    render(<FileDropzone file={null} onFile={onFile} />);
    const big = new File(["x"], "allure.json", { type: "application/json" });
    Object.defineProperty(big, "size", { value: MAX_UPLOAD_BYTES + 1 });
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [big] } });
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/máximo por subida es 4 MB/);
    expect(screen.getByRole("alert")).toHaveTextContent(/token de ingesta/);
  });
});

