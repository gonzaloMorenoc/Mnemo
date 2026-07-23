"use client";

import { ChevronRight, Menu, UserRound } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { OrgSwitcher } from "@/components/layout/org-switcher";
import { crumbForPath } from "@/components/layout/nav";
import { Button } from "@/components/ui/button";
import { truncate } from "@/lib/utils";

interface TopbarProps {
  onOpenMobileMenu: () => void;
}

export function Topbar({ onOpenMobileMenu }: TopbarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { signOut, user } = useAuth();

  // El header ya no repite el h1 de la página: es contexto (org) + ruta.
  const crumb = crumbForPath(pathname);

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-zinc-200/80 bg-[color:var(--surface)]/90 px-4 backdrop-blur md:px-6">
      <div className="flex min-w-0 items-center gap-1.5">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          onClick={onOpenMobileMenu}
          aria-label="Open menu"
        >
          <Menu size={16} />
        </Button>
        <OrgSwitcher />
        {crumb && (
          <nav
            aria-label="Ruta de navegación"
            className="flex min-w-0 items-center gap-1.5 text-sm"
          >
            <ChevronRight size={14} className="shrink-0 text-zinc-300" />
            {crumb.section && (
              <>
                <span className="hidden text-zinc-400 sm:inline">{crumb.section}</span>
                <ChevronRight size={14} className="hidden shrink-0 text-zinc-300 sm:inline" />
              </>
            )}
            <span className="truncate font-medium text-zinc-900">{crumb.label}</span>
          </nav>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <span className="hidden items-center gap-1 rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-600 sm:inline-flex">
          <UserRound size={12} />
          {truncate(user?.email ?? "unknown-user")}
        </span>
        <Button
          variant="outline"
          onClick={async () => {
            await signOut();
            router.replace("/login");
          }}
        >
          Cerrar sesión
        </Button>
      </div>
    </header>
  );
}
