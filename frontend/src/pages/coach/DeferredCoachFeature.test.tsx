import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { CompanyResearchPage } from "./CompanyResearchPage";
import { renderWithProviders } from "@/test/render";

describe("DeferredCoachFeature pages", () => {
  it("CompanyResearchPage honestly explains why it isn't available", () => {
    renderWithProviders(<CompanyResearchPage />);
    expect(screen.getByText("Company Research")).toBeInTheDocument();
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
    expect(screen.getByText(/never fabricate/i)).toBeInTheDocument();
  });
});
