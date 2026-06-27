"use client";

import { Menu, Sparkles } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { OrgSwitcher } from "@/components/layout/org-switcher";
import { Button } from "@/components/ui/button";
import { truncate } from "@/lib/utils";

const pageTitles: Record<string, string> = {
  "/app/knowledge": "Conocimiento",
  "/app/org": "Organization",
  "/app/settings": "Settings",
  "/app/test-plan": "Plan de pruebas",
};

interface TopbarProps {
  onOpenMobileMenu: () => void;
}

export function Topbar({ onOpenMobileMenu }: TopbarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { signOut, user } = useAuth();

  const title = pageTitles[pathname] ?? "Mnemo";

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-zinc-200/80 bg-[color:var(--surface)]/90 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={onOpenMobileMenu}
          aria-label="Open menu"
        >
          <Menu size={16} />
        </Button>
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-zinc-900">{title}</h1>
          <p className="hidden text-xs text-zinc-500 sm:block">
            Triaje determinista · aprobación humana · aseguramiento firmado
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <OrgSwitcher />
        <span className="hidden items-center gap-1 rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-600 sm:inline-flex">
          <Sparkles size={12} />
          {truncate(user?.email ?? "unknown-user")}
        </span>
        <Button
          variant="outline"
          onClick={async () => {
            await signOut();
            router.replace("/login");
          }}
        >
          Sign out
        </Button>
      </div>
    </header>
  );
}
