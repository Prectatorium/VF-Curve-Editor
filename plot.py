from __future__ import annotations

from typing import Sequence
import numpy as np
import matplotlib.pyplot as plt

from .model import VFEntry


def extract_curve(entries: Sequence[VFEntry]):
    volts = np.array([e.volt for e in entries])
    freqs = np.array([e.effective_freq for e in entries])
    return volts, freqs


def plot_curves(original, modified, *, show=True):
    v1, f1 = extract_curve(original)
    v2, f2 = extract_curve(modified)

    fig, ax = plt.subplots()

    orig_line, = ax.plot(v1, f1, label="Original", marker="o", markersize=3)
    mod_line,  = ax.plot(v2, f2, label="Modified", marker="o", markersize=3)

    ax.set_xlabel("Voltage (mV)")
    ax.set_ylabel("Frequency (MHz)")
    ax.set_title("VF Curve")
    ax.legend()
    ax.grid(True)

    # -------------------------
    # Hover annotation box
    # -------------------------
    annot = ax.annotate(
        "",
        xy=(0, 0),
        xytext=(15, 15),
        textcoords="offset points",
        bbox=dict(boxstyle="round", fc="black", alpha=0.7),
        color="white",
    )
    annot.set_visible(False)

    def nearest_point(x, y, xv, yv):
        idx = np.argmin((xv - x) ** 2 + (yv - y) ** 2)
        return idx

    def on_move(event):
        if event.inaxes != ax:
            annot.set_visible(False)
            fig.canvas.draw_idle()
            return

        x, y = event.xdata, event.ydata

        i1 = nearest_point(x, y, v1, f1)
        i2 = nearest_point(x, y, v2, f2)

        # decide which curve you're closer to
        d1 = (v1[i1] - x) ** 2 + (f1[i1] - y) ** 2
        d2 = (v2[i2] - x) ** 2 + (f2[i2] - y) ** 2

        if d1 < d2:
            vx, fy = v1[i1], f1[i1]
            label = "Original"
        else:
            vx, fy = v2[i2], f2[i2]
            label = "Modified"

        annot.xy = (vx, fy)
        annot.set_text(f"{label}\nV: {vx:.1f} mV\nF: {fy:.1f} MHz")
        annot.set_visible(True)

        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)

    if show:
        plt.show()

    return fig, ax
