import type {
  AuthState,
  ExportStatus,
  Facets,
  Health,
  ImportResult,
  ParseResult,
  PlaylistList,
  PreviewResponse,
  QuerySpec,
  SpotifyPlaylist,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      // Required by the API on every write; cross-site pages cannot add it.
      "X-PlaylistIQ": "1",
      ...(init?.headers ?? {}),
    },
    credentials: "same-origin",
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep the generic message
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>("/health"),
  me: () => request<AuthState>("/api/auth/me"),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  deleteMe: () => request<void>("/api/me", { method: "DELETE" }),
  playlists: () => request<PlaylistList>("/api/playlists"),
  spotifyPlaylists: () => request<SpotifyPlaylist[]>("/api/playlists/spotify"),
  sync: (id: string) => request<ImportResult>(`/api/playlists/${enc(id)}/sync`, { method: "POST" }),
  facets: (id: string) => request<Facets>(`/api/playlists/${enc(id)}/facets`),
  preview: (id: string, spec: QuerySpec) =>
    request<PreviewResponse>(`/api/playlists/${enc(id)}/preview`, {
      method: "POST",
      body: JSON.stringify(spec),
    }),
  parse: (playlistId: string, text: string) =>
    request<ParseResult>("/api/parse-query", {
      method: "POST",
      body: JSON.stringify({ playlist_id: playlistId, text }),
    }),
  startExport: (key: string, body: { playlist_id: string; spec: QuerySpec; name: string; description?: string }) =>
    request<ExportStatus>("/api/exports", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    }),
  getExport: (id: string) => request<ExportStatus>(`/api/exports/${enc(id)}`),
  retryExport: (id: string) => request<ExportStatus>(`/api/exports/${enc(id)}/retry`, { method: "POST" }),
};
