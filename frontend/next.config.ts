import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev-tools badge defaults to bottom-left — the Anvil launcher's spot.
  // Dev-only cosmetic, but it also blocks clicks in tests; move it clear.
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;
