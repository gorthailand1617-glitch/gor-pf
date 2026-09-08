import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.DOCKER_BUILD === "true" ? "standalone" : "export",
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
