import type { ReactNode } from "react";

export interface ShellProps {
  children: ReactNode;
}

export interface NavItem {
  href: string;
  label: string;
}

export interface ShellLink extends NavItem {
  active: boolean;
}
