"use client";

import { useRef, useState } from "react";
import { FileText, UploadCloud, X } from "lucide-react";

/**
 * Zona de subida con arrastrar-y-soltar. Sustituye al `<input type="file">`
 * nativo ("Seleccionar archivo Ningún archivo seleccionado"), que rompía el
 * pulido visual del resto de controles.
 */
export function FileDropzone({
  id,
  file,
  onFile,
  accept,
  hint,
}: {
  id?: string;
  file: File | null;
  onFile: (f: File | null) => void;
  accept?: string;
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={file ? `Archivo seleccionado: ${file.name}` : "Subir archivo"}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={`flex cursor-pointer items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-sm transition-colors ${
        dragging
          ? "border-zinc-900 bg-zinc-50"
          : "border-zinc-200 bg-white hover:border-zinc-400 hover:bg-zinc-50"
      }`}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      {file ? (
        <div className="flex w-full items-center gap-2 text-zinc-800">
          <FileText size={16} className="shrink-0 text-zinc-500" />
          <span className="truncate font-medium">{file.name}</span>
          <span className="text-xs text-zinc-400">
            {(file.size / 1024).toFixed(0)} KB
          </span>
          <button
            type="button"
            aria-label="Quitar archivo"
            className="ml-auto rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
            onClick={(e) => {
              e.stopPropagation();
              if (inputRef.current) inputRef.current.value = "";
              onFile(null);
            }}
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-1 text-zinc-500">
          <UploadCloud size={20} className="text-zinc-400" />
          <span>
            Arrastra el archivo aquí o <span className="font-medium text-zinc-800">haz clic para elegirlo</span>
          </span>
          {hint && <span className="text-xs text-zinc-400">{hint}</span>}
        </div>
      )}
    </div>
  );
}
