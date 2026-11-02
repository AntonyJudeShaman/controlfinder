import type { ReactNode } from "react";
import { JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { Shell } from "@/components/layout/Shell";
import { cn } from "@/lib/utils";
import "./globals.css";

const sans = Space_Grotesk({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata = { title: "ControlFinder", description: "Evaluated RAG over NIST SP 800-53 Rev 5" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={cn(sans.variable, mono.variable)}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
