/** Tokens from the CloudSense Figma file (UI workflow). Light theme only, as designed. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // surfaces + text
        paper: "#f4f6f5", panel: "#ffffff", rule: "#e1e7e5", track: "#eef2f1",
        ink: "#0c1a17", muted: "#5b6b66",
        // brand / status
        approve: "#0f766e", "approve-soft": "#8cc7bc", success: "#15803d",
        reject: "#b91c1c",
        learned: "#6d28d9", "learned-soft": "#ede9fe", "learned-card": "#fbfaff", "learned-line": "#ddd6fe",
        warn: "#b45309", "warn-soft": "#fef3c7",
        focus: "#0f766e",
        // sidebar
        side: { bg: "#0b1f1c", raised: "#16332e", avatar: "#2a4b45", text: "#9db5af", soft: "#cfe3de",
                active: "#5eead4", memory: "#c4b5fd" },
      },
      fontFamily: { sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"] },
      keyframes: { rise: { from: { opacity: "0", transform: "translateY(10px)" }, to: { opacity: "1", transform: "none" } } },
      animation: { rise: "rise 0.6s ease-out both" }, // the one orchestrated moment: the About hero demo
    },
  },
};
