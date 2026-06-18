import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ScoreCircle from "./ScoreCircle";

describe("ScoreCircle", () => {
  it("renders the numeric score", () => {
    render(<ScoreCircle score={75} />);
    expect(screen.getByText("75")).toBeInTheDocument();
  });

  it("renders /100 suffix", () => {
    render(<ScoreCircle score={50} />);
    expect(screen.getByText("/100")).toBeInTheDocument();
  });

  it("uses green border when score >= 65", () => {
    render(<ScoreCircle score={65} />);
    const circle = screen.getByText("65").closest(".score-circle");
    expect(circle).toHaveStyle("border-color: #22c55e");
  });

  it("uses yellow border when score >= 45 and < 65", () => {
    render(<ScoreCircle score={55} />);
    const circle = screen.getByText("55").closest(".score-circle");
    expect(circle).toHaveStyle("border-color: #f59e0b");
  });

  it("uses yellow border at boundary 45", () => {
    render(<ScoreCircle score={45} />);
    const circle = screen.getByText("45").closest(".score-circle");
    expect(circle).toHaveStyle("border-color: #f59e0b");
  });

  it("uses red border when score < 45", () => {
    render(<ScoreCircle score={44} />);
    const circle = screen.getByText("44").closest(".score-circle");
    expect(circle).toHaveStyle("border-color: #ef4444");
  });

  it("uses green border at maximum score 100", () => {
    render(<ScoreCircle score={100} />);
    const circle = screen.getByText("100").closest(".score-circle");
    expect(circle).toHaveStyle("border-color: #22c55e");
  });

  it("uses red border at score 0", () => {
    render(<ScoreCircle score={0} />);
    const circle = screen.getByText("0").closest(".score-circle");
    expect(circle).toHaveStyle("border-color: #ef4444");
  });
});
