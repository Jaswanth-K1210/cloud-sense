"""eval/plot.png: acceptance rate per scan, mean with min–max band across seeds.

    python -m eval.plot
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
# Validated categorical slots 1-2 (blue, orange) on a light surface.
STYLE = {"hindsight": ("#2a78d6", "With Hindsight memory"), "no_memory": ("#eb6834", "No memory")}
INK, MUTED, GRID = "#18212B", "#5C6A79", "#D5DCE3"


def plot(summary_path: Path = HERE / "results" / "summary.json", out: Path = HERE / "plot.png") -> Path:
    summary = json.loads(summary_path.read_text())
    fake = summary.get("meta", {}).get("fake", False)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    for cond, (color, label) in STYLE.items():
        if cond not in summary:
            continue
        if fake and cond == "hindsight":
            label = "With memory (in-memory fake)"
        s = summary[cond]
        x = list(range(1, len(s["acceptance_mean"]) + 1))
        mean = [v * 100 for v in s["acceptance_mean"]]
        lo = [(v if v is not None else m / 100) * 100 for v, m in zip(s["acceptance_min"], mean, strict=True)]
        hi = [(v if v is not None else m / 100) * 100 for v, m in zip(s["acceptance_max"], mean, strict=True)]
        ax.fill_between(x, lo, hi, color=color, alpha=0.15, linewidth=0)
        ax.plot(x, mean, color=color, linewidth=2, marker="o", markersize=5, markeredgecolor="white",
                markeredgewidth=1.5, label=label)
        ax.annotate(f"{label}  {mean[-1]:.0f}%", (x[-1], mean[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK)
    ax.set_ylim(0, 105)
    ax.set_xticks(x)
    ax.set_xlabel("Scan", color=MUTED)
    ax.set_ylabel("Recommendations approved (%)", color=MUTED)
    title = "Share of recommendations engineers approved, per scan (mean, min–max over seeds)"
    ax.set_title(title + ("\nOffline harness run: fake memory and fake LLM" if fake else ""),
                 fontsize=10, color=INK, loc="left")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(plot())
