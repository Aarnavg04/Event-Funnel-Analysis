"""The two README charts, drawn from reports/data/*.csv (no Snowflake needed).

Usage:
    .venv/bin/python src/plots.py      # after src/run_all.py

  reports/figures/retention_heatmap.png -- cohort x week, any-event retention.
      Unobserved cells are drawn as "not observed", never as 0 -- forgetting
      that is exactly the diagonal-cliff mistake decision 4.1 is about.
  reports/figures/mix_shift_bridge.png -- Oct -> Nov cart->purchase, split
      into mix / rate / interaction.

Colors are the dataviz reference palette: one-hue blue ramp for magnitude,
blue/red for up/down, text in ink colors rather than series colors.
"""

from __future__ import annotations

import csv
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

from config import REPO_ROOT

DATA = REPO_ROOT / "reports" / "data"
FIG = REPO_ROOT / "reports" / "figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8983"
GRID = "#e4e3df"
NEUTRAL = "#f0efec"
UP = "#2a78d6"
DOWN = "#e34948"
TOTAL = "#52514e"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "text.color": INK,
    "axes.labelcolor": INK_2,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "axes.edgecolor": GRID,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def read(name: str) -> list[dict]:
    with open(DATA / f"{name}.csv") as f:
        return list(csv.DictReader(f))


def retention_heatmap() -> None:
    rows = read("retention_matrix")
    cohorts = sorted({r["cohort_week"] for r in rows})
    n_weeks = len(cohorts)
    cell = {(r["cohort_week"], int(r["week_offset"])): float(r["retention_rate"]) for r in rows}
    size = {r["cohort_week"]: int(r["cohort_size"]) for r in rows}

    # Week 0 is 100% by construction. Coloring it would flatten every other
    # cell into the same pale band, so it is drawn neutral and the color
    # scale covers weeks 1+ only.
    later = [v for (c, w), v in cell.items() if w > 0]
    lo, hi = min(later), max(later)
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)

    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, c in enumerate(cohorts):
        y = n_weeks - 1 - i
        for w in range(n_weeks):
            if (c, w) not in cell:
                ax.add_patch(Rectangle((w, y), 1, 1, facecolor=SURFACE, edgecolor=GRID,
                                       hatch="////", linewidth=0))
                continue
            v = cell[(c, w)]
            if w == 0:
                fc, tc = NEUTRAL, INK_2
            else:
                t = (v - lo) / (hi - lo)
                fc = cmap(0.15 + 0.85 * t)
                tc = "white" if t > 0.45 else INK
            ax.add_patch(Rectangle((w, y), 1, 1, facecolor=fc, edgecolor=SURFACE, linewidth=2))
            ax.text(w + 0.5, y + 0.5, f"{v:.0%}" if w == 0 else f"{v:.1%}",
                    ha="center", va="center", color=tc, fontsize=10)

    ax.set_xlim(0, n_weeks)
    ax.set_ylim(0, n_weeks)
    ax.set_xticks([w + 0.5 for w in range(n_weeks)], [f"wk {w}" for w in range(n_weeks)])
    labels = [f"{date.fromisoformat(c):%b %-d}  (n={size[c]:,})" for c in cohorts]
    ax.set_yticks([n_weeks - 1 - i + 0.5 for i in range(n_weeks)], labels)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("weeks since the cohort's first week")

    fig.suptitle("Weekly retention by acquisition cohort (any event)", x=0.02, ha="left",
                 fontsize=13, fontweight="bold")
    fig.text(0.02, 0.9,
             "Hatched = not observed (data ends Nov 30), not zero. For the four oldest cohorts, the lowest week "
             "is the same\ncalendar week, Nov 19-25 (13.8-15.3%), right after the Nov 15-17 promo: "
             "a calendar effect, not aging.",
             ha="left", va="top", color=INK_2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.82))
    fig.savefig(FIG / "retention_heatmap.png", dpi=160)
    plt.close(fig)


def mix_shift_bridge() -> None:
    s = {r["metric"]: float(r["value"]) for r in read("mix_shift_summary")}
    pts = lambda k: 100 * s[k]
    steps = [
        ("October", pts("oct_rate"), "total"),
        ("Mix\n(category shares)", pts("mix"), "delta"),
        ("Rate\n(within category)", pts("rate"), "delta"),
        ("Interaction", pts("interaction"), "delta"),
        ("November", pts("nov_rate"), "total"),
    ]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    level = 0.0
    for i, (label, v, kind) in enumerate(steps):
        if kind == "total":
            bottom, height, color = 0, v, TOTAL
            level = v
            text, ty = f"{v:.2f}%", v + 0.8
        else:
            bottom = level + min(v, 0)
            height = abs(v)
            color = DOWN if v < 0 else UP
            text, ty = f"{v:+.2f} pts", level + max(v, 0) + 0.8
            level += v
        ax.bar(i, height, bottom=bottom, width=0.62, color=color, edgecolor=SURFACE, linewidth=2)
        ax.text(i, ty, text, ha="center", va="bottom", color=INK, fontsize=10, fontweight="bold")
        if i < len(steps) - 1:
            ax.plot([i + 0.31, i + 0.69], [level, level], color=INK_3, linewidth=1, linestyle=(0, (2, 2)))

    ax.set_xticks(range(len(steps)), [l for l, _, _ in steps])
    ax.set_ylim(0, 60)
    ax.set_ylabel("cart → purchase rate (%)")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)

    fig.suptitle("Why cart → purchase fell 14 points from October to November",
                 x=0.02, ha="left", fontsize=13, fontweight="bold")
    fig.text(0.02, 0.885,
             f"Mostly rate, not mix: every category converted worse. But Nov 15-17 promo carts converted at "
             f"{pts('spike_rate'):.1f}%;\nexcluding those 3 days, November is {pts('rest_nov_rate'):.1f}% "
             f"-- the spike accounts for {pts('spike_explains'):.1f} of the {-pts('delta'):.1f} points.",
             ha="left", va="top", color=INK_2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.80))
    fig.savefig(FIG / "mix_shift_bridge.png", dpi=160)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    retention_heatmap()
    mix_shift_bridge()
    print(f"wrote {FIG / 'retention_heatmap.png'}")
    print(f"wrote {FIG / 'mix_shift_bridge.png'}")


if __name__ == "__main__":
    main()
