import type { Metadata } from "next";

export const metadata: Metadata = { title: "Defect DNA" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
