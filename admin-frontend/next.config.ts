import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir:
    process.env.NODE_ENV === "development"
      ? ".next-admin-dev"
      : ".next-build"
};

export default nextConfig;
