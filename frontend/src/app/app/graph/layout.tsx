import type { Metadata } from "next";

export const metadata: Metadata = { title: "Grafo de conocimiento" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
