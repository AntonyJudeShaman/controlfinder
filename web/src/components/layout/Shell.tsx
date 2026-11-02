"use client";

import Link from "next/link";
import { useShell } from "@/hooks/components/layout/use-shell";
import { cn } from "@/lib/utils";
import type { ShellProps } from "@/types/components/layout/shell";

export function Shell({ children }: ShellProps) {
  const { links } = useShell();
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b-4 border-foreground bg-foreground text-background">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-end justify-between gap-4 px-6 py-5">
          <Link href="/" className="flex flex-col gap-1">
            <span className="text-4xl leading-none font-bold tracking-tighter uppercase">ControlFinder</span>
            <span className="font-mono text-xs tracking-widest text-background/70 uppercase">
              NIST SP 800-53 Rev 5 · evaluated RAG
            </span>
          </Link>
          <nav className="flex flex-wrap gap-2">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={link.active ? "page" : undefined}
                className={cn(
                  "border-2 border-background px-3 py-1.5 font-mono text-sm font-bold uppercase transition-colors",
                  link.active ? "bg-accent text-accent-foreground" : "hover:bg-background hover:text-foreground",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-8 px-6 py-8">{children}</main>
      <footer className="border-t-4 border-foreground bg-card">
        <div className="mx-auto w-full max-w-7xl px-6 py-3 font-mono text-xs uppercase">
          Every number on this site is read from results/ or the API.
        </div>
      </footer>
    </div>
  );
}
