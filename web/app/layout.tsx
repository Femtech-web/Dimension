import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Instrument_Serif } from "next/font/google";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import "./globals.css";

const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-serif" });
const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: { default: "Dimension", template: "%s · Dimension" },
  description:
    "Fe types that know which way value moves: the arithmetic behind Balancer V2's rounding and Moonwell's oracle pairing does not compile, and every claim is checked against the original code and the real chains.",
  openGraph: {
    title: "Dimension",
    description:
      "A Fe library in which the arithmetic behind two of DeFi's costliest recent failures does not compile. Reproduced on the real exploit, checked on the real chains.",
    type: "website",
  },
  twitter: { card: "summary" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <Nav />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
