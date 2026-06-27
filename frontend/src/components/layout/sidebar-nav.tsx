"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  BrainCircuit,
  Building2,
  ClipboardList,
  Dna,
  GraduationCap,
  Gauge,
  Home,
  Network,
  Plug,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/app/assurance", label: "Assurance", icon: ShieldCheck },
  { href: "/app/autopilot", label: "Autopilot", icon: Bot },
  { href: "/app/calibration", label: "Calibración", icon: Gauge },
  { href: "/app/defects", label: "Defect DNA", icon: Dna },
  { href: "/app/graph", label: "Knowledge Graph", icon: Network },
  { href: "/app/knowledge", label: "Conocimiento", icon: BrainCircuit },
  { href: "/app/onboarding", label: "Onboarding", icon: GraduationCap },
  { href: "/app/test-plan", label: "Plan de pruebas", icon: ClipboardList },
  { href: "/app/integrations", label: "Integrations", icon: Plug },
  { href: "/app/org", label: "Organization", icon: Building2 },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

interface SidebarNavProps {
  mobile?: boolean;
  onClose?: () => void;
}

export function SidebarNav({ mobile = false, onClose }: SidebarNavProps) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-5 py-5">
        <Link href="/" className="flex items-center gap-2" onClick={onClose}>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-900 text-white">
            <Home size={16} />
          </span>
          <span className="font-semibold tracking-tight text-zinc-900">Mnemo</span>
        </Link>
        {mobile && (
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close menu">
            <X size={16} />
          </Button>
        )}
      </div>

      <nav className="space-y-1 px-3">
        {navItems.map((item) => {
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
      </nav>

      <p className="mt-auto px-5 py-4 text-xs text-zinc-500">
        QA Autopilot · privado · on-premise · 0 € de API
      </p>
    </div>
  );
}
