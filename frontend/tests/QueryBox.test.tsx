import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { QueryBox } from "@/components/QueryBox";
import type { ParseResult } from "@/lib/types";

const ambiguous: ParseResult = {
  query: "only Echo",
  spec: null,
  draft_spec: null,
  resolved: [],
  ambiguities: [
    {
      text: "echo",
      polarity: "include",
      question: 'More than one artist called "Echo" is in this playlist.',
      options: [
        { id: "e1", name: "Echo", kind: "artist", entry_count: 40, detail: "appears on Waveform" },
        { id: "e2", name: "Echo", kind: "artist", entry_count: 50, detail: "appears on Feedback Loops" },
      ],
    },
  ],
  unrecognized: ["kendrick lamar"],
  unsupported: ["Play counts are not available from the Spotify Web API."],
  contradictions: [],
  notes: [],
  set_fields: [],
};

test("ambiguity, unknown names and unsupported requests are shown, not guessed", async () => {
  const user = userEvent.setup();
  const onApply = vi.fn();
  const onPick = vi.fn();
  render(<QueryBox onParse={async () => ambiguous} onApply={onApply} onPick={onPick} />);

  await user.type(screen.getByLabelText("Describe what you want"), "only Echo");
  await user.click(screen.getByRole("button", { name: "Apply" }));

  expect(await screen.findByText(/More than one artist called/)).toBeInTheDocument();
  expect(onApply).not.toHaveBeenCalled();
  expect(screen.getByText(/Not found in this playlist/)).toHaveTextContent("kendrick lamar");
  expect(screen.getByText(/Play counts/)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Feedback Loops/ }));
  expect(onPick).toHaveBeenCalledWith("include", ambiguous.ambiguities[0].options[1]);
});
