// Mirrors the FastAPI response models in backend/app/api/schemas.py.

export type ShuffleMode = "random" | "balanced" | "recently_added";

export interface QuerySpec {
  include_artist_ids: string[];
  exclude_artist_ids: string[];
  include_album_ids: string[];
  exclude_album_ids: string[];
  primary_artist_only: boolean;
  shuffle_mode: ShuffleMode;
  minimum_artist_gap: number;
  strict_constraints: boolean;
  seed: number | null;
  recently_added_band_days: number;
}

export const DEFAULT_SPEC: QuerySpec = {
  include_artist_ids: [],
  exclude_artist_ids: [],
  include_album_ids: [],
  exclude_album_ids: [],
  primary_artist_only: false,
  shuffle_mode: "balanced",
  minimum_artist_gap: 1,
  strict_constraints: false,
  seed: null,
  recently_added_band_days: 30,
};

export interface PlaylistSummary {
  id: string;
  name: string;
  description: string;
  entry_count: number;
  source: string;
}

export interface PlaylistList {
  mode: string;
  playlists: PlaylistSummary[];
}

export interface Artist {
  id: string | null;
  name: string;
}

export interface Album {
  id: string | null;
  name: string | null;
  album_type?: string | null;
}

export interface QueueItem {
  entry_id: string;
  position: number;
  queue_position: number;
  track_id: string | null;
  uri: string | null;
  name: string;
  artists: Artist[];
  album: Album | null;
  added_at: string | null;
  is_playable: boolean | null;
  is_local: boolean;
  duration_ms: number | null;
  match_reasons: string[];
}

export interface ArtistFacet {
  id: string;
  name: string;
  entry_count: number;
  is_local: boolean;
  detail: string;
}

export interface AlbumFacet {
  id: string;
  name: string;
  artist_names: string;
  entry_count: number;
}

export interface Facets {
  playlist_id: string;
  artists: ArtistFacet[];
  albums: AlbumFacet[];
}

export interface Violation {
  position: number;
  entry_id: string;
  conflicting_position: number;
  shared_artists: string[];
}

export type PreviewStatus = "ok" | "relaxed" | "infeasible" | "not_found";

export interface PreviewResponse {
  playlist_id: string;
  spec: QuerySpec;
  total_entries: number;
  match_count: number;
  removed_by_exclusion: number;
  mode: ShuffleMode;
  seed: number;
  status: PreviewStatus;
  applied_rules: string[];
  notes: string[];
  violations: Violation[];
  metrics: {
    adjacent_overlap_rate: number;
    same_artist_pairs_within_3: number;
    same_artist_pairs_within_5: number;
  };
  timing: { filter_ms: number; shuffle_ms: number; total_ms: number };
  queue: QueueItem[];
}

export interface EntityOption {
  id: string;
  name: string;
  kind: "artist" | "album";
  entry_count: number;
  detail: string;
}

export interface ParseResult {
  query: string;
  spec: QuerySpec | null;
  draft_spec: QuerySpec | null;
  resolved: { text: string; polarity: "include" | "exclude"; kind: "artist" | "album"; options: EntityOption[] }[];
  ambiguities: { text: string; polarity: "include" | "exclude"; question: string; options: EntityOption[] }[];
  unrecognized: string[];
  unsupported: string[];
  contradictions: string[];
  notes: string[];
  set_fields: string[];
}

export interface Health {
  status: string;
  demo_mode: boolean;
  spotify_configured: boolean;
}

export interface AuthState {
  spotify_configured: boolean;
  connected: boolean;
  display_name: string | null;
}

export interface SpotifyPlaylist {
  id: string;
  name: string;
  description: string;
  owner_name: string;
  item_count: number | null;
  readable: boolean;
  imported: boolean;
  synced_at: string | null;
}

export interface ImportResult {
  playlist_id: string;
  name: string;
  entry_count: number;
  skipped_unavailable: number;
  skipped_episodes: number;
}

export type ExportState = "pending" | "running" | "completed" | "failed";

export interface ExportStatus {
  id: string;
  status: ExportState;
  source_playlist_id: string;
  name: string;
  total_items: number;
  completed_items: number;
  skipped_items: number;
  batches_done: number;
  destination_playlist_id: string | null;
  destination_url: string | null;
  error: string | null;
  attempts: number;
}
