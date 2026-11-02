import type { NextConfig } from "next";

const API_URL = process.env.CONTROLFINDER_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default config;
