import { resolve } from "node:path";
import type { NextConfig } from "next";

const workspaceRoot = resolve(process.cwd(), "..");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@travelplanner/api-client"],
  outputFileTracingRoot: workspaceRoot,
  distDir:
    process.env.NEXT_DIST_DIR
    ?? (process.env.NODE_ENV === "development" ? ".next-dev" : ".next-build")
};

export default nextConfig;
