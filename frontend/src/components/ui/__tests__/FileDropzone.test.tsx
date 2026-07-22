// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FileDropzone } from "@/components/ui/file-dropzone";

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
});
