import type { Metadata } from "next";

export const metadata: Metadata = { title: "Onboarding al proyecto" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
