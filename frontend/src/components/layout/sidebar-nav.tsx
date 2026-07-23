"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { NAV_SECTIONS } from "@/components/layout/nav";

interface SidebarNavProps {
  mobile?: boolean;
  onClose?: () => void;
}

export function SidebarNav({ mobile = false, onClose }: SidebarNavProps) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-5 py-5">
        <Link href="/app" className="flex items-center gap-2" onClick={onClose}>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-900 text-white">
            <LayoutDashboard size={16} />
          </span>
          <span className="font-semibold tracking-tight text-zinc-900">Mnemo</span>
        </Link>
        {mobile && (
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close menu">
            <X size={16} />
          </Button>
        )}
      </div>

      <nav aria-label="Principal" className="space-y-4 px-3">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title ?? "home"} className="space-y-1">
            {section.title && (
              <p className="px-3 pt-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
                {section.title}
              </p>
            )}
            {section.items.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition",
                    active
                      ? "bg-zinc-900 text-white"
                      : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900",
                  )}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <p className="mt-auto px-5 py-4 text-xs text-zinc-500">
        Mnemo · QA Memory
      </p>
    </div>
  );
}
