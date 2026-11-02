import { usePathname } from "next/navigation";
import { shellLinks } from "@/lib/components/layout/shell-helpers";
import type { ShellLink } from "@/types/components/layout/shell";

export function useShell(): { links: ShellLink[] } {
  return { links: shellLinks(usePathname()) };
}
