"""
arps-decline.py
---------------
Auto Arps decline curve fitting and forecast for oil/gas wells.

Usage:
    python arps-decline.py                        # demo with synthetic data
    python arps-decline.py --csv production.csv   # fit from CSV
    python arps-decline.py --csv production.csv --forecast 60 --plot

CSV format expected:
    date,production      (date: YYYY-MM-DD, production: bbl/d or mcf/d)
  OR:
    month,production     (month: integer 0, 1, 2, ...)

Outputs:
    - Best-fit decline type and parameters printed to console
    - arps_forecast.csv  with fitted + forecasted production
    - arps_plot.png      if --plot flag is used
"""

import argparse
import csv
import math
import os
import sys
from datetime import datetime, timedelta

# ── optional imports ───────────────────────────────────────────────────────────
try:
    import numpy as np
    from scipy.optimize import curve_fit
    from scipy.stats import pearsonr
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("WARNING: numpy/scipy not found. Install with:  pip install numpy scipy")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ══════════════════════════════════════════════════════════════════════════════
# Arps decline models
# ══════════════════════════════════════════════════════════════════════════════

def exponential(t, qi, di):
    """q(t) = qi * exp(-Di * t)  [b = 0]"""
    return qi * np.exp(-di * t)


def hyperbolic(t, qi, di, b):
    """q(t) = qi / (1 + b*Di*t)^(1/b)  [0 < b < 2]"""
    b = np.clip(b, 1e-6, 1.9999)
    return qi / (1.0 + b * di * t) ** (1.0 / b)


def harmonic(t, qi, di):
    """q(t) = qi / (1 + Di*t)  [b = 1]"""
    return qi / (1.0 + di * t)


# ══════════════════════════════════════════════════════════════════════════════
# Cumulative production
# ══════════════════════════════════════════════════════════════════════════════

def cum_exponential(t, qi, di):
    """Gp or Np = qi/Di * (1 - exp(-Di*t))"""
    return (qi / di) * (1.0 - np.exp(-di * t))


def cum_hyperbolic(t, qi, di, b):
    """Gp = qi^b / ((1-b)*Di) * [qi^(1-b) - q(t)^(1-b)]"""
    b = np.clip(b, 1e-6, 1.9999)
    qt = hyperbolic(t, qi, di, b)
    return (qi ** b / ((1.0 - b) * di)) * (qi ** (1.0 - b) - qt ** (1.0 - b))


def cum_harmonic(t, qi, di):
    """Gp = qi/Di * ln(1 + Di*t)"""
    return (qi / di) * np.log(1.0 + di * t)


# ══════════════════════════════════════════════════════════════════════════════
# Fitting
# ══════════════════════════════════════════════════════════════════════════════

def r_squared(y_actual, y_predicted):
    ss_res = np.sum((y_actual - y_predicted) ** 2)
    ss_tot = np.sum((y_actual - np.mean(y_actual)) ** 2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def fit_all(t, q):
    """Fit exponential, hyperbolic, and harmonic. Return best fit."""
    qi_guess = float(q[0])
    di_guess = 0.05
    results = {}

    # ── Exponential ──
    try:
        popt, _ = curve_fit(
            exponential, t, q,
            p0=[qi_guess, di_guess],
            bounds=([0, 1e-6], [qi_guess * 5, 2.0]),
            maxfev=5000
        )
        q_fit = exponential(t, *popt)
        results["exponential"] = {
            "params": {"qi": popt[0], "di": popt[1], "b": 0.0},
            "r2": r_squared(q, q_fit),
            "q_fit": q_fit,
            "func": lambda t_, p=popt: exponential(t_, *p),
            "cum_func": lambda t_, p=popt: cum_exponential(t_, *p),
        }
    except Exception:
        pass

    # ── Harmonic ──
    try:
        popt, _ = curve_fit(
            harmonic, t, q,
            p0=[qi_guess, di_guess],
            bounds=([0, 1e-6], [qi_guess * 5, 2.0]),
            maxfev=5000
        )
        q_fit = harmonic(t, *popt)
        results["harmonic"] = {
            "params": {"qi": popt[0], "di": popt[1], "b": 1.0},
            "r2": r_squared(q, q_fit),
            "q_fit": q_fit,
            "func": lambda t_, p=popt: harmonic(t_, *p),
            "cum_func": lambda t_, p=popt: cum_harmonic(t_, *p),
        }
    except Exception:
        pass

    # ── Hyperbolic ──
    try:
        popt, _ = curve_fit(
            hyperbolic, t, q,
            p0=[qi_guess, di_guess, 0.8],
            bounds=([0, 1e-6, 0.01], [qi_guess * 5, 2.0, 1.99]),
            maxfev=10000
        )
        q_fit = hyperbolic(t, *popt)
        results["hyperbolic"] = {
            "params": {"qi": popt[0], "di": popt[1], "b": popt[2]},
            "r2": r_squared(q, q_fit),
            "q_fit": q_fit,
            "func": lambda t_, p=popt: hyperbolic(t_, p[0], p[1], p[2]),
            "cum_func": lambda t_, p=popt: cum_hyperbolic(t_, p[0], p[1], p[2]),
        }
    except Exception:
        pass

    if not results:
        raise RuntimeError("All curve fits failed. Check your input data.")

    best = max(results, key=lambda k: results[k]["r2"])
    return best, results


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

def load_csv(path):
    """Load production CSV. Returns (t_months, q_rates, dates_or_None)."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in reader.fieldnames]
        prod_col = next((h for h in headers if "prod" in h or "rate" in h or "boe" in h or "mcf" in h or "bbl" in h), None)
        time_col = next((h for h in headers if "date" in h or "month" in h or "time" in h or "period" in h), None)
        if prod_col is None or time_col is None:
            raise ValueError(f"Could not identify time/production columns. Headers: {reader.fieldnames}")
        for row in reader:
            rows.append((row[time_col].strip(), float(row[prod_col].strip())))

    dates = []
    t_months = []
    q_rates = []
    for i, (time_val, q) in enumerate(rows):
        q_rates.append(q)
        # try parsing as date
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y"):
            try:
                dates.append(datetime.strptime(time_val, fmt))
                break
            except ValueError:
                continue
        else:
            try:
                t_months.append(float(time_val))
                dates.append(None)
            except ValueError:
                t_months.append(float(i))
                dates.append(None)

    # derive t_months from dates if we have them
    if dates[0] is not None:
        t0 = dates[0]
        t_months = [(d - t0).days / 30.4375 for d in dates]

    return np.array(t_months, dtype=float), np.array(q_rates, dtype=float), dates if dates[0] else None


def synthetic_data(seed=42):
    """Generate hyperbolic decline data with noise."""
    np.random.seed(seed)
    t = np.arange(0, 36, 1.0)
    qi, di, b = 1200.0, 0.10, 0.85
    q_true = hyperbolic(t, qi, di, b)
    noise = np.random.normal(0, q_true * 0.04)
    q_obs = np.clip(q_true + noise, 1, None)
    dates = [datetime(2022, 1, 1) + timedelta(days=int(m * 30.4375)) for m in t]
    return t, q_obs, dates, {"qi": qi, "di": di, "b": b}


# ══════════════════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════════════════

ANNUAL_DI_NOTE = """  (Di expressed as monthly fraction; annualized Di = 1-(1-Di)^12)"""

def print_results(best, results, t, q):
    bar = "═" * 56
    print(f"\n{bar}")
    print("  ARPS DECLINE CURVE ANALYSIS")
    print(bar)
    print(f"  Data points : {len(t)}")
    print(f"  Time range  : {t[0]:.1f} – {t[-1]:.1f} months")
    print(f"  Rate range  : {q.min():.0f} – {q.max():.0f} (units as input)")
    print(f"\n  {'Model':<14}  {'R²':>6}  {'qi':>10}  {'Di/mo':>8}  {'b':>6}")
    print(f"  {'-'*14}  {'-'*6}  {'-'*10}  {'-'*8}  {'-'*6}")
    for name, res in results.items():
        p = res["params"]
        flag = " ◄ best" if name == best else ""
        print(f"  {name:<14}  {res['r2']:6.4f}  {p['qi']:10.1f}  {p['di']:8.4f}  {p['b']:6.3f}{flag}")
    print()
    best_p = results[best]["params"]
    di_annual = 1 - (1 - best_p["di"]) ** 12
    print(f"  Best fit    : {best.upper()}")
    print(f"  qi          : {best_p['qi']:,.1f}")
    print(f"  Di (monthly): {best_p['di']:.4f}  ({best_p['di']*100:.2f}%/mo)")
    print(f"  Di (annual) : {di_annual:.4f}  ({di_annual*100:.1f}%/yr)")
    print(f"  b exponent  : {best_p['b']:.3f}")
    print(bar)


def write_forecast_csv(path, t_hist, q_hist, dates_hist, t_fore, q_fore, dates_fore, best, results):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month", "date", "actual_rate", "fitted_rate", "forecast_rate",
                    "cum_production", "period"])
        q_fit_hist = results[best]["q_fit"]
        cum_func = results[best]["cum_func"]

        for i, (t_val, q_act) in enumerate(zip(t_hist, q_hist)):
            date_str = dates_hist[i].strftime("%Y-%m-%d") if dates_hist else ""
            q_fit_val = q_fit_hist[i]
            cum = cum_func(np.array([t_val]))[0]
            w.writerow([f"{t_val:.1f}", date_str, f"{q_act:.2f}", f"{q_fit_val:.2f}", "", f"{cum:.0f}", "history"])

        last_t = t_hist[-1]
        for i, (t_val, q_val) in enumerate(zip(t_fore, q_fore)):
            date_str = dates_fore[i].strftime("%Y-%m-%d") if dates_fore else ""
            cum = cum_func(np.array([t_val]))[0]
            w.writerow([f"{t_val:.1f}", date_str, "", "", f"{q_val:.2f}", f"{cum:.0f}", "forecast"])

    print(f"  Saved forecast: {path}")


def plot_results(t_hist, q_hist, t_fore, q_fore, results, best, dates_hist, output_path):
    if not HAS_MPL:
        print("  matplotlib not available — skipping plot.")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle("Arps Decline Curve Analysis", fontsize=14, fontweight="bold")

    # x axis labels
    if dates_hist:
        x_hist = [d.strftime("%Y-%m") for d in dates_hist]
        fore_start = dates_hist[-1]
        x_fore = [(fore_start + timedelta(days=int((t - t_hist[-1]) * 30.4375))).strftime("%Y-%m")
                  for t in t_fore]
        x_ticks = list(range(0, len(x_hist) + len(x_fore), max(1, (len(x_hist)+len(x_fore))//8)))
        all_x = x_hist + x_fore
    else:
        x_hist = t_hist
        x_fore = t_fore
        all_x = None

    # Rate plot
    idx_hist = range(len(t_hist))
    idx_fore = range(len(t_hist), len(t_hist) + len(t_fore))

    ax1.scatter(idx_hist, q_hist, color="#2196F3", s=20, zorder=5, label="Actual")
    for name, res in results.items():
        style = "-" if name == best else "--"
        alpha = 1.0 if name == best else 0.4
        color = "#E53935" if name == best else "gray"
        ax1.plot(idx_hist, res["q_fit"], style, color=color, alpha=alpha,
                 label=f"{name} (R²={res['r2']:.4f})")
    ax1.plot(idx_fore, q_fore, "-", color="#E53935", linewidth=2, label="Forecast")
    ax1.axvline(len(t_hist) - 0.5, color="black", linewidth=1, linestyle=":", alpha=0.5)
    ax1.set_ylabel("Production Rate")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f"Best fit: {best.title()}  |  b={results[best]['params']['b']:.3f}  "
                  f"Di={results[best]['params']['di']*100:.2f}%/mo")

    # Cumulative plot
    cum_func = results[best]["cum_func"]
    all_t = np.concatenate([t_hist, t_fore])
    all_idx = range(len(all_t))
    cum_all = cum_func(all_t)
    ax2.plot(all_idx, cum_all / 1000, color="#43A047", linewidth=2, label="Cumulative (×1,000)")
    ax2.axvline(len(t_hist) - 0.5, color="black", linewidth=1, linestyle=":", alpha=0.5)
    ax2.set_ylabel("Cumulative Production (×1,000)")
    ax2.set_xlabel("Month")
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=8)

    # x tick labels
    if dates_hist:
        tick_positions = list(range(0, len(all_x), max(1, len(all_x)//8)))
        ax2.set_xticks(tick_positions)
        ax2.set_xticklabels([all_x[i] for i in tick_positions], rotation=30, ha="right")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved plot   : {output_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Auto Arps Decline Curve Analysis")
    parser.add_argument("--csv", help="Path to production CSV file")
    parser.add_argument("--forecast", type=int, default=24, help="Months to forecast (default: 24)")
    parser.add_argument("--plot", action="store_true", help="Save a plot as arps_plot.png")
    parser.add_argument("--out", default="arps_forecast.csv", help="Output CSV path")
    args = parser.parse_args()

    if not HAS_SCIPY:
        sys.exit("numpy and scipy are required. Run:  pip install numpy scipy")

    # ── Load data ──
    demo_true = None
    if args.csv:
        print(f"\nLoading: {args.csv}")
        t, q, dates = load_csv(args.csv)
    else:
        print("\nNo --csv provided. Running with synthetic hyperbolic data (demo mode).")
        t, q, dates, demo_true = synthetic_data()

    # ── Filter zeros / negatives ──
    mask = q > 0
    t, q = t[mask], q[mask]
    if dates:
        dates = [d for d, m in zip(dates, mask) if m]

    if len(t) < 4:
        sys.exit("Need at least 4 non-zero production months to fit a decline curve.")

    # ── Fit ──
    print(f"\nFitting Arps models to {len(t)} months of data...")
    best, results = fit_all(t, q)

    # ── Print results ──
    print_results(best, results, t, q)
    if demo_true:
        print(f"  (True params: qi={demo_true['qi']}, Di={demo_true['di']}, b={demo_true['b']})")

    # ── Forecast ──
    dt = t[1] - t[0] if len(t) > 1 else 1.0
    t_fore = np.arange(t[-1] + dt, t[-1] + dt + args.forecast * dt, dt)
    q_fore = results[best]["func"](t_fore)

    if dates:
        last_date = dates[-1]
        dates_fore = [last_date + timedelta(days=int((tt - t[-1]) * 30.4375)) for tt in t_fore]
    else:
        dates_fore = None

    # ── Summary ──
    total_hist_cum = results[best]["cum_func"](np.array([t[-1]]))[0]
    total_fore_cum = results[best]["cum_func"](np.array([t_fore[-1]]))[0] - total_hist_cum
    print(f"\n  Forecast summary ({args.forecast} months):")
    print(f"    Rate at start of forecast : {q_fore[0]:,.0f}")
    print(f"    Rate at end of forecast   : {q_fore[-1]:,.0f}")
    print(f"    Incremental cum. forecast : {total_fore_cum:,.0f}")
    print(f"    Historic cum. (fitted)    : {total_hist_cum:,.0f}")

    # ── Outputs ──
    write_forecast_csv(args.out, t, q, dates, t_fore, q_fore, dates_fore, best, results)

    if args.plot:
        plot_out = args.out.replace(".csv", ".png") if args.out.endswith(".csv") else "arps_plot.png"
        plot_results(t, q, t_fore, q_fore, results, best, dates, plot_out)

    print()


if __name__ == "__main__":
    main()
