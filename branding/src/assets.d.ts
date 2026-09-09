/**
 * Asset imports resolve to a URL string at build time.
 *
 * Declared locally rather than pulling in `vite/client`, so this package stays
 * free of a bundler dependency.
 */
declare module "*.svg" {
  const url: string;
  export default url;
}
