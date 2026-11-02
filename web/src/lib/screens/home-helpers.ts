import type { HomeSection } from "@/types/screens/home";

export const HOME_SECTIONS: readonly HomeSection[] = [
  { href: "/controls", title: "Controls", blurb: "Browse and search the catalog the system retrieves from." },
  { href: "/configs", title: "Configs", blurb: "Every setup tested, which one production uses, and live knobs." },
  { href: "/results", title: "Results", blurb: "Every metric with its 95% interval, dev against sealed test." },
  { href: "/ask", title: "Ask", blurb: "Get a cited answer, or a refusal when the evidence is not there." },
  { href: "/trace", title: "Trace", blurb: "Replay the agent's steps for any logged request." },
];
