import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DownloadExcelButton } from "./DownloadExcelButton";

describe("DownloadExcelButton", () => {
  it("calls onDownload when clicked", async () => {
    const onDownload = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<DownloadExcelButton onDownload={onDownload} />);

    await user.click(screen.getByRole("button", { name: /download excel/i }));
    expect(onDownload).toHaveBeenCalledOnce();
  });

  it("renders a custom label", () => {
    render(
      <DownloadExcelButton onDownload={vi.fn()} label="Download submissions (Excel)" />,
    );
    expect(
      screen.getByRole("button", { name: /download submissions/i }),
    ).toBeInTheDocument();
  });

  it("shows an error message when the download fails", async () => {
    const onDownload = vi.fn().mockRejectedValue(new Error("HTTP 500"));
    const user = userEvent.setup();
    render(<DownloadExcelButton onDownload={onDownload} />);

    await user.click(screen.getByRole("button", { name: /download excel/i }));
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });
});
