from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from .parser import parse_entries
from .transform import apply_shift_to_entries
from .model import ShiftConfig, CurveConfig
from .serializer import serialize_blob


class VFCurveApp:
    def __init__(self, root, blob_hex: str):
        self.root = root

        # IMPORTANT: keep original blob for proper serialization
        self.original_blob_hex = blob_hex

        self.entries = parse_entries(blob_hex)
        self.current_entries = self.entries

        self.shift = tk.IntVar(value=0)
        self.peak = tk.DoubleVar(value=0.0)
        self.power = tk.DoubleVar(value=1.0)

        self._build_ui()
        self._update_plot()

    # ---------------- UI ----------------

    def _build_ui(self):
        self.root.title("VF Curve Editor")

        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(side="left", fill="y")

        ttk.Label(controls, text="Shift").pack()
        ttk.Scale(
            controls,
            from_=0,
            to=20,
            variable=self.shift,
            command=self._on_change,
        ).pack()

        ttk.Label(controls, text="Peak MHz").pack()
        ttk.Scale(
            controls,
            from_=-200,
            to=200,
            variable=self.peak,
            command=self._on_change,
        ).pack()

        ttk.Label(controls, text="Power").pack()
        ttk.Scale(
            controls,
            from_=0.1,
            to=3.0,
            variable=self.power,
            command=self._on_change,
        ).pack()

        ttk.Button(
            controls,
            text="Commit Changes",
            command=self._commit,
        ).pack(pady=10)

        ttk.Button(
            controls,
            text="Exit",
            command=self._on_close,
        ).pack(pady=5)

        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.get_tk_widget().pack(side="right", fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- Core compute ----------------

    def _compute(self):
        config = ShiftConfig(
            shift_steps=self.shift.get(),
            curve_config=CurveConfig(
                peak_mhz=self.peak.get(),
                power=self.power.get(),
            ),
        )

        new_entries, _ = apply_shift_to_entries(self.entries, config)
        return new_entries

    # ---------------- Plot ----------------

    def _update_plot(self):
        self.ax.clear()

        self.current_entries = self._compute()
        new_entries = self.current_entries

        v1 = [e.volt for e in self.entries]
        f1 = [e.effective_freq for e in self.entries]

        v2 = [e.volt for e in new_entries]
        f2 = [e.effective_freq for e in new_entries]

        self.ax.plot(v1, f1, label="Original")
        self.ax.plot(v2, f2, label="Modified")

        self.ax.set_xlabel("Voltage (mV)")
        self.ax.set_ylabel("Frequency (MHz)")
        self.ax.legend()
        self.ax.grid(True)

        self.canvas.draw()

    def _on_change(self, _=None):
        self._update_plot()

    # ---------------- Commit ----------------

    def _commit(self):
        try:
            blob = serialize_blob(
                self.original_blob_hex,
                self.current_entries,
            )

            out_file = "vf_curve_modified.txt"
            with open(out_file, "w", encoding="ascii") as f:
                f.write(blob)

            try:
                import pyperclip
                pyperclip.copy(blob)
            except Exception:
                pass

            messagebox.showinfo(
                "Committed",
                f"Saved to {out_file}"
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Exit ----------------

    def _on_close(self):
        try:
            plt.close(self.fig)
        except Exception:
            pass

        self.root.quit()
        self.root.destroy()


def launch_gui(blob_hex: str):
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    root = tk.Tk()
    app = VFCurveApp(root, blob_hex)
    root.mainloop()
