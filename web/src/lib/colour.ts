// Team colours come from MatchInfo and can be anything. These helpers keep text legible.

function parseHex(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m || !m[1]) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const rgb = parseHex(hex);
  if (!rgb) return 0;
  const [r, g, b] = rgb;
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Ink or chalk, whichever reads better on top of `bg`. */
export function textOn(bg: string, ink = '#0d1220', chalk = '#f2f4f8'): string {
  return contrast(bg, ink) >= contrast(bg, chalk) ? ink : chalk;
}

/** Mix a colour towards white until it reaches `target` contrast against `ground`. */
export function legibleOn(hex: string, ground: string, target = 4.5): string {
  const rgb = parseHex(hex);
  if (!rgb) return '#f2f4f8';
  for (let t = 0; t <= 1.0001; t += 0.05) {
    const mixed = rgb.map((c) => Math.round(c + (255 - c) * t));
    const out = '#' + mixed.map((c) => c.toString(16).padStart(2, '0')).join('');
    if (contrast(out, ground) >= target) return out;
  }
  return '#ffffff';
}
