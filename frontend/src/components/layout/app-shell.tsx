"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { SidebarNav } from "@/components/layout/sidebar-nav";
import { Topbar } from "@/components/layout/topbar";
import { OrgProvider } from "@/components/providers/org-provider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative min-h-screen bg-[color:var(--background)]">
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[252px_1fr]">
        <aside className="hidden border-r border-zinc-200 bg-white md:block">
          <SidebarNav />
        </aside>

        <main className="relative min-w-0">
          <OrgProvider>
            <Topbar onOpenMobileMenu={() => setMobileOpen(true)} />
            <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8">{children}</div>
          </OrgProvider>
        </main>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.button
              className="fixed inset-0 z-30 bg-zinc-950/35 md:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation overlay"
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-40 w-72 border-r border-zinc-200 bg-white md:hidden"
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: "spring", stiffness: 240, damping: 28 }}
            >
              <SidebarNav mobile onClose={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
