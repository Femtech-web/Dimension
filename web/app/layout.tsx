import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Instrument_Serif } from "next/font/google";
import { Nav } from "@/components/Nav";
import { differential } from "@/lib/results";
import { REPO } from "@/lib/site";
import "./globals.css";

const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-serif" });
const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: { default: "Dimension", template: "%s · Dimension" },
  description:
    "Fe types that know which way value moves: the arithmetic behind Balancer V2's rounding and Moonwell's oracle pairing does not compile, and every claim is checked against the original code and the real chains.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <Nav />
        <main>{children}</main>
        <footer style={{ borderTop: "1px solid var(--rule)", padding: "36px 0 56px" }}>
          <div className="wrap" style={{ display: "flex", flexWrap: "wrap", gap: 24, justifyContent: "space-between" }}>
            <span className="muted mono" style={{ fontSize: 13 }}>
              Fe {differential.fe.version} ({differential.fe.commit.slice(0, 7)}) · every measured result on this site is
              rendered from a report in docs/results
            </span>
            <span className="mono" style={{ fontSize: 13 }}>
              <a href={REPO}>Source</a> · <a href={`${REPO}/blob/main/JUDGES.md`}>JUDGES.md</a> · Apache-2.0 and GPL-3.0
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
