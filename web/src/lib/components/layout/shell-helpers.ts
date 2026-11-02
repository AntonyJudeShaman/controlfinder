import type { NavItem, ShellLink } from "@/types/components/layout/shell";

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/controls", label: "Controls" },
  { href: "/configs", label: "Configs" },
  { href: "/results", label: "Results" },
  { href: "/ask", label: "Ask" },
  { href: "/trace", label: "Trace" },
];

export function shellLinks(pathname: string): ShellLink[] {
  return NAV_ITEMS.map((item) => ({ ...item, active: pathname.startsWith(item.href) }));
}
