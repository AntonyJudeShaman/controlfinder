import Link from "next/link";
import { HOME_SECTIONS } from "@/lib/screens/home-helpers";

export function Home() {
  return (
    <>
      <section className="flex flex-col gap-4 border-b-4 border-foreground pb-8">
        <span className="w-fit bg-accent px-2 py-0.5 font-mono text-xs font-bold tracking-widest uppercase">
          Evaluated RAG
        </span>
        <h1 className="max-w-4xl text-6xl leading-[0.95] font-bold tracking-tighter uppercase">
          Find the NIST control. Cite it. Or say no.
        </h1>
        <p className="max-w-3xl text-lg text-muted-foreground">
          ControlFinder answers questions about NIST SP 800-53 Rev 5 with citations to the controls it used, and refuses
          when the evidence is weak. NIST&apos;s own cross-references are the answer key, so every setting was chosen
          by measurement, not by feel.
        </p>
      </section>
      <nav className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {HOME_SECTIONS.map((section) => (
          <Link
            key={section.href}
            href={section.href}
            className="group flex flex-col gap-3 border-3 border-foreground bg-card p-5 shadow-brutal transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:bg-accent"
          >
            <span className="text-3xl font-bold tracking-tighter uppercase">{section.title} →</span>
            <span className="text-muted-foreground group-hover:text-foreground">{section.blurb}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
