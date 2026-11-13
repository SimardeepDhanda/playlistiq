import { render, screen } from "@testing-library/react";
import { QueuePreview } from "@/components/QueuePreview";
import { DEFAULT_SPEC, type PreviewResponse } from "@/lib/types";

const base: PreviewResponse = {
  playlist_id: "p",
  spec: DEFAULT_SPEC,
  total_entries: 10,
  match_count: 2,
  removed_by_exclusion: 0,
  mode: "balanced",
  seed: 42,
  status: "relaxed",
  applied_rules: ["Only songs where any credited artist is: A"],
  notes: ["1 placements break the gap of 1; each one is listed."],
  violations: [{ position: 1, entry_id: "p:1", conflicting_position: 0, shared_artists: ["A"] }],
  metrics: { adjacent_overlap_rate: 1, same_artist_pairs_within_3: 1, same_artist_pairs_within_5: 1 },
  timing: { filter_ms: 0.1, shuffle_ms: 0.1, total_ms: 0.2 },
  queue: [0, 1].map((i) => ({
    entry_id: `p:${i}`,
    position: i,
    queue_position: i,
    track_id: `t${i}`,
    uri: null,
    name: `Song ${i}`,
    artists: [{ id: "a", name: "A" }],
    album: { id: "al", name: "Album" },
    added_at: null,
    is_playable: true,
    is_local: false,
    duration_ms: 185000,
    match_reasons: [],
  })),
};

test("shows counts, rules, seed and flags each spacing break", () => {
  render(<QueuePreview preview={base} />);
  expect(screen.getByTestId("match-count")).toHaveTextContent("2");
  expect(screen.getByTestId("status")).toHaveTextContent("Spacing not fully met");
  expect(screen.getByTestId("rules")).toHaveTextContent("A");
  expect(screen.getByText(/Seed 42/)).toBeInTheDocument();
  expect(screen.getByText("close to #1")).toBeInTheDocument();
  expect(screen.getAllByText("3:05")).toHaveLength(2);
});

test("infeasible result shows the reason and no queue", () => {
  render(
    <QueuePreview
      preview={{ ...base, status: "infeasible", queue: [], violations: [], notes: ["A gap of 8 is impossible"] }}
    />,
  );
  expect(screen.getByTestId("status")).toHaveTextContent("Impossible with these rules");
  expect(screen.getByTestId("notes")).toHaveTextContent("impossible");
  expect(screen.queryByTestId("queue")).not.toBeInTheDocument();
});
