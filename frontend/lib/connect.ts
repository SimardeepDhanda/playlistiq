/**
 * Start Spotify sign-in. Spotify only accepts the 127.0.0.1 redirect address, and
 * cookies are per host name, so a visitor on "localhost" is moved to 127.0.0.1 first.
 */
export function connectSpotify(): void {
  const { hostname, port, protocol } = window.location;
  const base = hostname === "localhost" ? `${protocol}//127.0.0.1${port ? `:${port}` : ""}` : "";
  // A real page load is required: this is an API route that redirects to Spotify.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.href = `${base}/api/auth/spotify/start`;
}
