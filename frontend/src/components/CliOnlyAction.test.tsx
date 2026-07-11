import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CliOnlyAction } from "./CliOnlyAction";

describe("CliOnlyAction", () => {
  it("renders disabled, naming the real CLI command in its title", () => {
    render(<CliOnlyAction command="career-agent submit --review-session x">Submit</CliOnlyAction>);
    const button = screen.getByRole("button", { name: /submit/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", expect.stringContaining("career-agent submit"));
  });
});
