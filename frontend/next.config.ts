import type { NextConfig } from "next";

// In Docker, the backend is reachable at http://backend:8000 over the compose
// network; locally it's http://localhost:8000. BACKEND_URL is read at server
// start (rewrites run at runtime), so compose can inject the right value.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
