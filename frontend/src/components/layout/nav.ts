import {
  BadgeCheck,
  BookMarked,
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
  {
    title: null,
    items: [
      { href: "/app", label: "Dashboard", icon: LayoutDashboard },
      { href: "/app/guia", label: "Guía", icon: BookMarked },
    ],
  },
  {
    title: "Memoria",
    items: [
      { href: "/app/knowledge", label: "Conocimiento", icon: BrainCircuit },
      { href: "/app/onboarding", label: "Onboarding al proyecto", icon: GraduationCap },
      { href: "/app/graph", label: "Grafo de conocimiento", icon: Network },
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
      { href: "/app/verify", label: "Verificar acta", icon: BadgeCheck },
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

export type Crumb = { section: string | null; label: string };

/**
 * Resuelve el breadcrumb de una ruta con prefix-match segmentado:
 * "/app/defects/123" → { section: "Aseguramiento", label: "Defect DNA" }.
 * "/app" (Dashboard) solo casa con la ruta exacta para no absorber rutas desconocidas.
 */
export function crumbForPath(pathname: string): Crumb | null {
  let best: { section: string | null; href: string; label: string } | null = null;
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      const matches =
        pathname === item.href ||
        (item.href !== "/app" && pathname.startsWith(`${item.href}/`));
      if (matches && (!best || item.href.length > best.href.length)) {
        best = { section: section.title, href: item.href, label: item.label };
      }
    }
  }
  return best ? { section: best.section, label: best.label } : null;
}
