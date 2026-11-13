import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ExportPanel } from "@/components/ExportPanel";
import { api } from "@/lib/api";
import { DEFAULT_SPEC, type ExportStatus, type PreviewResponse } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  api: { startExport: vi.fn(), getExport: vi.fn(), retryExport: vi.fn() },
}));

const preview = {
  playlist_id: "abc",
  spec: { ...DEFAULT_SPEC, seed: 7 },
  queue: [
    { entry_id: "a", uri: "spotify:track:1", is_local: false },
    { entry_id: "b", uri: "spotify:track:2", is_local: false },
    { entry_id: "c", uri: null, is_local: true },
  ],
} as unknown as PreviewResponse;

const job = (over: Partial<ExportStatus>): ExportStatus => ({
  id: "job1",
  status: "running",
  source_playlist_id: "abc",
  name: "Mix",
  total_items: 2,
  completed_items: 0,
  skipped_items: 1,
  batches_done: 0,
  destination_playlist_id: "dest",
  destination_url: "https://open.spotify.com/playlist/dest",
  error: null,
  attempts: 1,
  ...over,
});

test("demo playlists cannot be exported", () => {
  render(<ExportPanel preview={preview} playlistName="Demo" live={false} />);
  expect(screen.getByRole("button", { name: "Export to Spotify" })).toBeDisabled();
});

test("export asks for confirmation, then shows progress and the link", async () => {
  const user = userEvent.setup();
  vi.mocked(api.startExport).mockResolvedValue(job({}));
  vi.mocked(api.getExport).mockResolvedValue(job({ status: "completed", completed_items: 2 }));
  render(<ExportPanel preview={preview} playlistName="Mine" live />);

  expect(screen.getByText(/1 local files or unavailable items/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Export to Spotify" }));
  expect(screen.getByRole("alertdialog")).toHaveTextContent("with 2 songs");
  expect(api.startExport).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: "Create playlist" }));
  const [key, body] = vi.mocked(api.startExport).mock.calls[0];
  expect(key).toMatch(/^[0-9a-f]{32}$/);
  expect(body.spec.seed).toBe(7);

  await waitFor(() => expect(screen.getByText(/Done: 2 songs added/)).toBeInTheDocument(), { timeout: 3000 });
  expect(screen.getByRole("link", { name: "Open in Spotify" })).toHaveAttribute(
    "href",
    "https://open.spotify.com/playlist/dest",
  );
});

test("a failed export offers a retry that continues the same playlist", async () => {
  const user = userEvent.setup();
  vi.mocked(api.startExport).mockResolvedValue(job({ status: "failed", completed_items: 1, error: "Spotify returned an error" }));
  vi.mocked(api.retryExport).mockResolvedValue(job({ status: "completed", completed_items: 2 }));
  render(<ExportPanel preview={preview} playlistName="Mine" live />);
  await user.click(screen.getByRole("button", { name: "Export to Spotify" }));
  await user.click(screen.getByRole("button", { name: "Create playlist" }));
  expect(await screen.findByText(/Stopped after 1 of 2/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Retry/ }));
  expect(api.retryExport).toHaveBeenCalledWith("job1");
  expect(await screen.findByText(/Done: 2 songs/)).toBeInTheDocument();
});
