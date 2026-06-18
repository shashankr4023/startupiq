/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) so the Docker
  // runtime image can be tiny - it copies only the traced dependencies, not
  // the whole node_modules. No effect on `npm run dev`.
  output: "standalone",
};

export default nextConfig;
