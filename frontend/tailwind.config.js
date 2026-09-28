/** Colors come from CSS variables in src/index.css so light/dark swap in one place. */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: v("ink"), muted: v("muted"), paper: v("paper"), panel: v("panel"), rule: v("rule"),
        approve: v("approve"), reject: v("reject"), learned: v("learned"), focus: v("focus"),
      },
      fontFamily: {
        sans: ['"Schibsted Grotesk"', "ui-sans-serif", "system-ui", "sans-serif"],
        voice: ['"Newsreader"', "Georgia", "serif"],
      },
    },
  },
};
