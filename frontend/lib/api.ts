import type { Facets, Health, ParseResult, PlaylistList, PreviewResponse, QuerySpec } from "./types";

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
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
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
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  playlists: () => request<PlaylistList>("/api/playlists"),
  facets: (id: string) => request<Facets>(`/api/playlists/${encodeURIComponent(id)}/facets`),
  preview: (id: string, spec: QuerySpec) =>
    request<PreviewResponse>(`/api/playlists/${encodeURIComponent(id)}/preview`, {
      method: "POST",
      body: JSON.stringify(spec),
    }),
  parse: (playlistId: string, text: string) =>
    request<ParseResult>("/api/parse-query", {
      method: "POST",
      body: JSON.stringify({ playlist_id: playlistId, text }),
    }),
};
