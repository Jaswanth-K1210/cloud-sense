import type { CSSProperties } from "react";

// SVGs exported from the CloudSense Figma file. They are used as masks, so the exact Figma geometry can be
// painted in any colour (Figma exports one file per colour).
const urls = import.meta.glob("../assets/icons/*.svg", { eager: true, import: "default" }) as Record<string, string>;
const src = (name: string) => urls[`../assets/icons/${name}.svg`];

// Placement copied from the Figma layers, normalised to a 16px box:
// `box` = the icon group's inset, `pad` = the group's negative inset (stroke overhang).
const GEOMETRY: Record<string, { box: string; pad: [number, number, number, number]; file?: string }> = {
  cloud: { box: "20.83% 8.33% 20.83% 8.34%", pad: [10.71, 7.5, 10.71, 7.5] },
  chev: { box: "37.5% 25% 37.5% 25%", pad: [28.57, 14.29, 28.57, 14.29] },
  dash: { box: "12.5%", pad: [8.33, 8.33, 8.33, 8.33] },
  inbox: { box: "16.67% 8.33%", pad: [9.38, 7.5, 9.37, 7.5] },
  net: { box: "8.33%", pad: [7.5, 7.5, 7.5, 7.5] },
  shield: { box: "8.33% 16.67% 8.32% 16.67%", pad: [7.5, 9.37, 7.5, 9.37] },
  book: { box: "12.5% 8.33%", pad: [8.33, 7.5, 8.33, 7.5] },
  msg: { box: "12.47% 12.47% 8.33% 8.33%", pad: [7.89, 7.89, 7.89, 7.89] },
  act: { box: "12.5% 8.33%", pad: [8.33, 7.5, 8.33, 7.5] },
  sliders: { box: "8.33% 12.5%", pad: [7.5, 8.33, 7.5, 8.33] },
  sparkles: { box: "12.5% 8.33% 4.17% 20.83%", pad: [7.5, 8.82, 7.5, 8.82] },
  eye: { box: "20.83% 8.33%", pad: [10.72, 7.5, 10.72, 7.5], file: "eye-amber" },
  bell: { box: "8.33% 12.5% 8.31% 12.5%", pad: [7.5, 8.33, 7.5, 8.33] },
  alert: { box: "12.44% 8.34% 12.5% 8.26%", pad: [8.33, 7.49, 8.33, 7.49], file: "alert-amber" },
};

export type IconName = keyof typeof GEOMETRY;

export function Icon({ name, size = 16, className = "", style }: {
  name: IconName; size?: number; className?: string; style?: CSSProperties;
}) {
  const g = GEOMETRY[name];
  const k = 16 / size; // stroke overhang grows as the icon shrinks
  const [t, r, b, l] = g.pad.map((p) => `-${(p * k).toFixed(2)}%`);
  const url = `url("${src(g.file ?? name)}")`; // quoted: Vite inlines small SVGs as data: URLs
  return (
    <span aria-hidden="true" className={`relative inline-block shrink-0 overflow-hidden ${className}`}
      style={{ width: size, height: size, ...style }}>
      <span className="absolute" style={{ inset: g.box }}>
        <span className="absolute bg-current"
          style={{ inset: `${t} ${r} ${b} ${l}`, maskImage: url, WebkitMaskImage: url, maskSize: "100% 100%",
            WebkitMaskSize: "100% 100%", maskRepeat: "no-repeat", WebkitMaskRepeat: "no-repeat" }} />
      </span>
    </span>
  );
}
