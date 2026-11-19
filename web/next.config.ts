import { execSync } from "node:child_process";
import type { NextConfig } from "next";

// The commit this build comes from: Vercel's, or the local checkout's.
function git(args: string): string {
  try {
    return execSync(`git ${args}`, { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "";
  }
}
const vercel = process.env.VERCEL_GIT_COMMIT_SHA ?? "";
const commit = vercel || git("rev-parse HEAD");
const dirty = !vercel && commit !== "" && git("status --porcelain") !== "";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_COMMIT: commit, NEXT_PUBLIC_COMMIT_DIRTY: dirty ? "1" : "0" },
  poweredByHeader: false,
  reactStrictMode: true,
  // web/ is the app's root; the repository's root holds the Fe workspace.
  turbopack: { root: process.cwd() },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async redirects() {
    return [{ source: "/judges", destination: "/verify", permanent: true }];
  },
};

export default nextConfig;
