import { describe, expect, it } from "vitest";
import { link } from "../src/lib/tools/FeatureLinkerUnlabeledKD";

const f = (uniqueId: string, rt: number, mz: number, intensity: number, charge = 1) =>
  ({ uniqueId, rt, mz, intensity, charge, quality: 0, width: 0, boundingBox: null, metaValues: {} }) as any;

describe("feature linking stand-in", () => {
  it("links the closest features within tolerance, one per map", () => {
    const groups = link(
      [
        [f("a1", 100, 500.0, 10), f("a2", 300, 600.0, 5)],
        [f("b1", 110, 500.002, 8), f("b2", 105, 500.0, 1, 2), f("b3", 900, 600.0, 4)],
      ],
      { rtTol: 30, mzTol: 10, ppm: true, chargeMerging: "With_charge_zero" },
    );
    const ids = groups.map((g) => g.elements.map((e) => e.id).join("+")).sort();
    // b2 has another charge; b3 is outside the RT window
    expect(ids).toEqual(["a1+b1", "a2", "b2", "b3"]);
    expect(groups.every((g) => g.quality >= 0 && g.quality <= 1)).toBe(true);
  });
});
