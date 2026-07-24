export type Block =
  | { kind: "p"; text: string } // párrafo con inline-lite
  | { kind: "steps"; items: string[] } // pasos numerados
  | { kind: "list"; items: string[] } // viñetas
  | { kind: "note"; tone: "info" | "warn"; text: string } // aviso
  | { kind: "term"; term: string }; // definición destacada (del GLOSSARY)

export type Section = { heading?: string; blocks: Block[] };

export type Chapter = {
  slug: string;
  title: string;
  summary: string;
  sections: Section[];
};
