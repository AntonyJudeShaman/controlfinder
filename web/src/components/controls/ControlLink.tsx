import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { ControlLinkProps } from "@/types/components/controls/control-link";

export function ControlLink({ control, invalid = false }: ControlLinkProps) {
  return (
    <Link href={`/controls?id=${encodeURIComponent(control.control_id)}`} className="group flex items-baseline gap-2">
      <Badge variant={invalid ? "destructive" : "outline"}>{control.display_id}</Badge>
      <span className="group-hover:underline">{control.title ?? "not in the catalog"}</span>
    </Link>
  );
}
