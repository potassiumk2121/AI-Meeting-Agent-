/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async redirects() {
    return [{ source: "/login", destination: "/dashboard", permanent: false }];
  },
};

module.exports = nextConfig;
