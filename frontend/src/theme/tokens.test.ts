/// <reference types="node" />
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { macaronTokens } from "./tokens";

function luminance(hex: string): number {
  const rgb = hex.slice(1).match(/../g)!.map((part) => {
    const value = parseInt(part, 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0]! * 0.2126 + rgb[1]! * 0.7152 + rgb[2]! * 0.0722;
}

const css = readFileSync("src/styles/tokens.css", "utf8");

describe("design token contract", () => {
  it("mirrors every radius and both shadow elevations", () => {
    expect(css).toContain(`--opanel-font-family: ${macaronTokens.fontFamily};`);
    for (const [name, value] of Object.entries(macaronTokens.radius)) {
      expect(css).toContain(`--opanel-radius-${name}: ${value};`);
    }
    for (const theme of ["light", "dark"] as const) {
      expect(css).toContain(`--opanel-shadow-sm: ${macaronTokens.shadowSm[theme]};`);
      expect(css).toContain(`--opanel-shadow: ${macaronTokens.shadow[theme]};`);
    }
  });

  for (const theme of ["light", "dark"] as const) {
    it(`${theme} text and tone pairs meet WCAG AA and mirror CSS`, () => {
      const palette = macaronTokens[theme];
      const themeCss = css.split('}')[theme === "light" ? 0 : 1]!;
      for (const [name, value] of Object.entries(palette)) {
        const cssName = name === "canvas" ? "bg" : name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
        expect(themeCss).toContain(`--opanel-${cssName}: ${value};`);
      }
      for (const [name, tone] of Object.entries(macaronTokens.tones)) {
        expect(themeCss).toContain(`--opanel-tone-${name}-bg: ${tone[theme].bg};`);
        expect(themeCss).toContain(`--opanel-tone-${name}-text: ${tone[theme].text};`);
      }
      expect(themeCss).toContain(`--opanel-shadow-sm: ${macaronTokens.shadowSm[theme]};`);
      expect(themeCss).toContain(`--opanel-shadow: ${macaronTokens.shadow[theme]};`);
      const pairs = [
        ["text/canvas", palette.text, palette.canvas],
        ["muted/canvas", palette.muted, palette.canvas],
        ["muted/panelSolid", palette.muted, palette.panelSolid],
        ...Object.entries(macaronTokens.tones).map(([name, tone]) => [name, tone[theme].text, tone[theme].bg]),
      ];
      for (const [name, foreground, background] of pairs) {
        const values = [luminance(foreground!), luminance(background!)].sort((a, b) => b - a);
        const ratio = (values[0]! + 0.05) / (values[1]! + 0.05);
        expect(ratio, `${theme} ${name}: ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
      }
    });
  }
});
