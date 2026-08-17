import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { HomePage } from "./HomePage";

describe("HomePage", () => {
  it("presents GeoPilot as evidence-first decision support without implying statutory approval", () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", {
        name: /evidence-first planning intelligence/i,
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/does not grant statutory approval/i),
    ).toBeInTheDocument();
  });
});