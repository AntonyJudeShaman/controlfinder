import type { PageHeaderProps } from "@/types/components/layout/page-header";

export function PageHeader({ kicker, title, children }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-3 border-b-4 border-foreground pb-6">
      <span className="w-fit bg-accent px-2 py-0.5 font-mono text-xs font-bold tracking-widest uppercase">
        {kicker}
      </span>
      <h1 className="text-5xl leading-none font-bold tracking-tighter uppercase">{title}</h1>
      {children ? <div className="max-w-3xl text-base text-muted-foreground">{children}</div> : null}
    </div>
  );
}
