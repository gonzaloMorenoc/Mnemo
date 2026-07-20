import {
  BadgeCheck,
  Bot,
  BrainCircuit,
  Building2,
  ClipboardList,
  Dna,
  GraduationCap,
  Gauge,
  LayoutDashboard,
  Network,
  Plug,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };
export type NavSection = { title: string | null; items: NavItem[] };

export const NAV_SECTIONS: NavSection[] = [
  { title: null, items: [{ href: "/app", label: "Dashboard", icon: LayoutDashboard }] },
  {
    title: "Memoria",
    items: [
      { href: "/app/knowledge", label: "Conocimiento", icon: BrainCircuit },
      { href: "/app/onboarding", label: "Onboarding", icon: GraduationCap },
      { href: "/app/graph", label: "Knowledge Graph", icon: Network },
      { href: "/app/test-plan", label: "Plan de pruebas", icon: ClipboardList },
    ],
  },
  {
    title: "Aseguramiento",
    items: [
      { href: "/app/assurance", label: "Assurance", icon: ShieldCheck },
      { href: "/app/autopilot", label: "Autopilot", icon: Bot },
      { href: "/app/defects", label: "Defect DNA", icon: Dna },
      { href: "/app/calibration", label: "Calibración", icon: Gauge },
      { href: "/verify", label: "Verificar acta", icon: BadgeCheck },
    ],
  },
  {
    title: "Configuración",
    items: [
      { href: "/app/integrations", label: "Integraciones", icon: Plug },
      { href: "/app/org", label: "Organización", icon: Building2 },
      { href: "/app/settings", label: "Ajustes", icon: Settings },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export function labelForPath(pathname: string): string | null {
  return NAV_ITEMS.find((i) => i.href === pathname)?.label ?? null;
}
