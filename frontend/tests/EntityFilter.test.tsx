import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { EntityFilter } from "@/components/EntityFilter";
import { setState, stateOf } from "@/lib/spec";
import { DEFAULT_SPEC, type QuerySpec } from "@/lib/types";

const rows = [
  { id: "a1", name: "Marlo Vance", count: 290 },
  { id: "a2", name: "Echo", detail: "appears on Waveform", count: 40 },
  { id: "a3", name: "Echo", detail: "appears on Feedback Loops", count: 50 },
];

function Harness({ onSpec }: { onSpec: (s: QuerySpec) => void }) {
  const [spec, setSpec] = useState(DEFAULT_SPEC);
  return (
    <EntityFilter
      label="Artists"
      rows={rows}
      stateOf={(id) => stateOf(spec, "artist", id)}
      onChange={(id, st) => {
        const next = setState(spec, "artist", id, st);
        setSpec(next);
        onSpec(next);
      }}
    />
  );
}

test("include, switch to exclude, then clear", async () => {
  const user = userEvent.setup();
  let spec = DEFAULT_SPEC;
  render(<Harness onSpec={(s) => (spec = s)} />);

  await user.click(screen.getByRole("button", { name: "Include Marlo Vance" }));
  expect(spec.include_artist_ids).toEqual(["a1"]);
  expect(screen.getByText("Only Marlo Vance")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Exclude Marlo Vance" }));
  expect(spec.include_artist_ids).toEqual([]);
  expect(spec.exclude_artist_ids).toEqual(["a1"]);

  await user.click(screen.getByRole("button", { name: "Remove rule for Marlo Vance" }));
  expect(spec.exclude_artist_ids).toEqual([]);
});

test("same-named artists are told apart and searchable", async () => {
  const user = userEvent.setup();
  render(<Harness onSpec={() => {}} />);
  await user.type(screen.getByPlaceholderText("Search artists"), "echo");
  expect(screen.queryByText("Marlo Vance")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Include Echo (appears on Waveform)" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Include Echo (appears on Feedback Loops)" })).toBeInTheDocument();
});

test("an id is never both included and excluded", () => {
  let s = setState(DEFAULT_SPEC, "album", "x", "include");
  s = setState(s, "album", "x", "exclude");
  expect(s.include_album_ids).toEqual([]);
  expect(s.exclude_album_ids).toEqual(["x"]);
});
