"""
OrcaFlex Workflow — Step 3: Results Report (Post-Processing)
============================================================
Use-cases covered
  FOWT        : platform 6-DOF motions, mooring utilisation, cable integrity,
                extreme statistics for ULS design checks
  Marine Ops  : crane tip / suspended load dynamics, wire tension, operability
                (adapt object names and result variables as needed)

Sections
  1. Static equilibrium results
  2. Platform / vessel motions  (6-DOF time histories)
  3. Mooring system             (all legs: tension envelope, utilisation vs MBL)
  4. Dynamic cable              (tension, minimum bend radius, touchdown point)
  5. Linked statistics          (correlated variable queries, spectral moments)
  6. Fatigue — rainflow half-cycles
  7. Extreme statistics         (Rayleigh fits, MPM, risk-factor extremes,
                                 aggregated across all seeds if n_seeds > 1)

Public API
  post_process(sim_paths, params, out_dir) -> dict
      Generate the text report + figures, return paths of all artefacts.

Standalone CLI: loads testModel.sim, post-processes with project_config
  defaults, writes results_report.txt and fig*.png next to this file.
"""

import math
import os
import sys
from contextlib import redirect_stdout

import OrcFxAPI
import numpy as np

from project_config import params_with_defaults


def _mask_fpu_exceptions():
    """Mask all x87 FPU exceptions on Windows.

    matplotlib (via NumPy/contourpy on import) and a few SciPy ops unmask
    floating-point exceptions in the MSVC runtime; subsequent OrcFxAPI calls
    then trip 'Windows fatal exception: code 0xc0000090' (FLT_INVALID_OP).
    Re-mask after every matplotlib import that precedes an OrcFxAPI call.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # _MCW_EM = 0x0008001F  → mask = all-FP-exceptions-masked
        ctypes.cdll.msvcrt._controlfp(0x0008001F, 0x0008001F)
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════════════════════
# Tee: mirror writes to console + file
# ══════════════════════════════════════════════════════════════════════════════
class _Tee:
    def __init__(self, stream1, stream2):
        self._s1, self._s2 = stream1, stream2
    def write(self, data):
        self._s1.write(data)
        self._s2.write(data)
        return len(data)
    def flush(self):
        self._s1.flush()
        self._s2.flush()
    def isatty(self):
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Constants & helpers
# ══════════════════════════════════════════════════════════════════════════════
DOF_VARS = [
    ("Surge (X)",   "X"),
    ("Sway  (Y)",   "Y"),
    ("Heave (Z)",   "Z"),
    ("Roll  (R1)",  "Rotation 1"),
    ("Pitch (R2)",  "Rotation 2"),
    ("Yaw   (R3)",  "Rotation 3"),
]
DOF_UNITS = {"X": "m", "Y": "m", "Z": "m",
             "Rotation 1": "deg", "Rotation 2": "deg", "Rotation 3": "deg"}


def _rayleigh_extremes(obj, var_name, period, storm_hours, risk_pct, oe=None):
    kwargs = {"objectExtra": oe} if oe is not None else {}
    ext    = obj.ExtremeStatistics(var_name, period, **kwargs)
    out    = {}
    for label, tail in [("upper", OrcFxAPI.DistributionTail.Upper),
                        ("lower", OrcFxAPI.DistributionTail.Lower)]:
        ext.Fit(OrcFxAPI.RayleighStatisticsSpecification(tail))
        r = ext.Query(OrcFxAPI.RayleighStatisticsQuery(storm_hours, risk_pct))
        out[label] = (r.MostProbableExtremeValue, r.ExtremeValueWithRiskFactor)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Report writer (single sim)
# ══════════════════════════════════════════════════════════════════════════════
def _run_report(model, cfg: dict):
    """Print the full text report. Returns a context dict for plotting."""
    period      = cfg["period"]
    mooring_mbl = cfg["mooring_mbl"]
    cable_mbr   = cfg["cable_mbr"]
    storm_hours = cfg["storm_hours"]
    risk_pct    = cfg["risk_pct"]

    platform = model["Platform"]
    cable    = model["ExportCable"]
    env      = model.environment

    water_depth = float(env.WaterDepth)

    mooring_lines = [obj for obj in model.objects if obj.Name.startswith("Mooring")]
    mooring_rg = {ml.Name: ml.RangeGraph("Effective tension", period)
                  for ml in mooring_lines}

    print(f"Simulation loaded.  State: {model.state.name}")
    print(f"  Mooring lines found: {[ml.Name for ml in mooring_lines]}")
    print(f"  Water depth        : {water_depth:.1f} m")
    t = platform.SampleTimes(period)
    print(f"  Analysis window    : {t[0]:.1f} s – {t[-1]:.1f} s  ({len(t)} samples)")

    SEP = "=" * 65

    # ── SECTION 1 — Static Equilibrium ────────────────────────────────────────
    print(f"\n{SEP}\nSECTION 1 — Static Equilibrium\n{SEP}")
    print("\n  Platform mean position (static):")
    for var in ("X", "Y", "Z"):
        print(f"    {var} = {platform.StaticResult(var):.3f} m")

    print("\n  Mooring static tensions:")
    print(f"  {'Line':<12}  {'EndA (kN)':>12}  {'EndB (kN)':>12}  {'Delta_horiz (m)':>16}")
    for ml in mooring_lines:
        Te_A = ml.StaticResult("Effective tension", OrcFxAPI.oeEndA)
        Te_B = ml.StaticResult("Effective tension", OrcFxAPI.oeEndB)
        xA = ml.StaticResult("X", OrcFxAPI.oeEndA)
        yA = ml.StaticResult("Y", OrcFxAPI.oeEndA)
        xB = ml.StaticResult("X", OrcFxAPI.oeEndB)
        yB = ml.StaticResult("Y", OrcFxAPI.oeEndB)
        dH = math.hypot(xB - xA, yB - yA)
        print(f"  {ml.Name:<12}  {Te_A:12.1f}  {Te_B:12.1f}  {dH:16.1f}")

    # ── SECTION 2 — Platform Motions ─────────────────────────────────────────
    print(f"\n{SEP}\nSECTION 2 — Platform Motions  (stage {period})\n{SEP}")
    print(f"\n  {'DOF':<14}  {'Mean':>9}  {'Std':>9}  {'Min':>9}  {'Max':>9}  {'Range':>9}")
    for label, var in DOF_VARS:
        th = np.asarray(platform.TimeHistory(var, period))
        print(f"  {label:<14}  {th.mean():9.3f}  {th.std():9.3f}  "
              f"{th.min():9.3f}  {th.max():9.3f}  {np.ptp(th):9.3f}")

    elev = env.TimeHistory("Elevation", period, OrcFxAPI.oeEnvironment(0.0, 0.0, 0.0))
    print(f"\n  Measured Hs (4σ at origin) = {4*np.std(elev):.2f} m  "
          f"(target = {env.WaveHs:.2f} m)")

    # ── SECTION 3 — Mooring System ───────────────────────────────────────────
    print(f"\n{SEP}\nSECTION 3 — Mooring System  (stage {period})\n{SEP}")
    print(f"\n  MBL = {mooring_mbl:.0f} kN")
    print(f"\n  {'Line':<12}  {'Te_max (kN)':>12}  {'UT_max (%)':>11}  "
          f"{'Arc of max (m)':>15}  {'Te_min (kN)':>12}")
    for ml in mooring_lines:
        rg = mooring_rg[ml.Name]
        idx_max = int(np.argmax(rg.Max))
        Te_max  = rg.Max[idx_max]
        UT_max  = 100.0 * Te_max / mooring_mbl
        arc_max = rg.X[idx_max]
        Te_min  = float(np.min(rg.Min))
        print(f"  {ml.Name:<12}  {Te_max:12.1f}  {UT_max:10.1f}%  "
              f"{arc_max:15.1f}  {Te_min:12.1f}")

    print("\n  Linked statistics at fairlead (arc 0 m ≡ End A):")
    print(f"  {'Line':<12}  {'MaxTe (kN)':>12}  {'X@MaxTe (m)':>13}  {'t_max (s)':>10}")
    for ml in mooring_lines:
        ls = ml.LinkedStatistics(("Effective tension", "X"), period, OrcFxAPI.oeEndA)
        q  = ls.Query("Effective tension", "X")
        print(f"  {ml.Name:<12}  {q.ValueAtMax:12.1f}  {q.LinkedValueAtMax:13.2f}  "
              f"{q.TimeOfMax:10.2f}")

    # ── SECTION 4 — Dynamic Export Cable ─────────────────────────────────────
    print(f"\n{SEP}\nSECTION 4 — Dynamic Export Cable  (stage {period})\n{SEP}")
    rg_cable = cable.RangeGraph("Effective tension", period)
    idx_max  = int(np.argmax(rg_cable.Max))
    print("\n  Tension envelope:")
    print(f"    Peak max tension : {rg_cable.Max[idx_max]:.1f} kN  "
          f"at arc = {rg_cable.X[idx_max]:.1f} m")
    print(f"    Global min tension: {float(np.min(rg_cable.Min)):.1f} kN")

    rg_curv  = cable.RangeGraph("Curvature", period)
    max_curv = float(np.max(rg_curv.Max))
    mbr_dyn  = 1.0 / max_curv
    arc_mbr  = rg_curv.X[int(np.argmax(rg_curv.Max))]
    flag     = "FAIL ✗" if mbr_dyn < cable_mbr else "PASS ✓"
    print(f"\n  Minimum dynamic bend radius : {mbr_dyn:.2f} m  "
          f"(limit = {cable_mbr:.2f} m)  [{flag}]  at arc = {arc_mbr:.1f} m")

    rg_z   = cable.RangeGraph("Z", period)
    z_tol  = 1.0
    seabed = -water_depth
    tdp_arc = next((x for x, z in zip(rg_z.X, rg_z.Mean) if z <= seabed + z_tol),
                   None)
    if tdp_arc is None:
        print("\n  Touchdown point not detected (cable does not reach seabed).")
    else:
        print(f"\n  Approximate TDP arc length  : {tdp_arc:.1f} m")

    # ── SECTION 5 — Linked statistics & spectral moments ─────────────────────
    print(f"\n{SEP}\nSECTION 5 — Linked Statistics (cable at mid-buoyancy section)\n{SEP}")
    section_lengths = list(cable.Length)
    arc_mid = sum(section_lengths[:1]) + section_lengths[1] / 2.0
    oe_mid  = OrcFxAPI.oeArcLength(arc_mid)

    ls_cable = cable.LinkedStatistics(
        ("Effective tension", "Bend moment"), period, oe_mid
    )
    q_te = ls_cable.Query("Effective tension", "Bend moment")
    tss  = ls_cable.TimeSeriesStatistics("Effective tension")

    print(f"\n  At arc = {arc_mid:.1f} m (mid of buoyancy section):")
    print(f"    Max tension          : {q_te.ValueAtMax:.1f} kN   at t = {q_te.TimeOfMax:.1f} s")
    print(f"    Bend moment at max Te: {q_te.LinkedValueAtMax:.2f} kN·m")
    print(f"    Min tension          : {q_te.ValueAtMin:.1f} kN   at t = {q_te.TimeOfMin:.1f} s")
    print("\n  Spectral moments of tension at mid-section:")
    print(f"    Mean      = {tss.Mean:.2f} kN")
    print(f"    Std dev   = {tss.StdDev:.2f} kN")
    print(f"    Tz (zero-up-crossing period) = {tss.Tz:.2f} s")
    print(f"    Tc (crest period)            = {tss.Tc:.2f} s")
    print(f"    Bandwidth ε                  = {tss.Bandwidth:.4f}")

    # ── SECTION 6 — Fatigue (rainflow) ───────────────────────────────────────
    print(f"\n{SEP}\nSECTION 6 — Fatigue: Rainflow Half-Cycles\n{SEP}")
    print("\n  Platform heave rainflow (stage 1):")
    ranges_z = list(platform.RainflowHalfCycles("Z", period))
    print(f"    Half-cycles  : {len(ranges_z)}")
    if ranges_z:
        print(f"    Largest range: {max(ranges_z):.3f} m")
        bins = np.linspace(0.0, max(ranges_z), 7)
        counts, _ = np.histogram(ranges_z, bins=bins)
        for i, c in enumerate(counts):
            print(f"    [{bins[i]:.2f} – {bins[i+1]:.2f} m]  {c:>5} half-cycles")

    most_loaded = max(mooring_lines,
                      key=lambda ml: float(np.max(mooring_rg[ml.Name].Max)))
    print(f"\n  Mooring tension rainflow — {most_loaded.Name} at End A (stage 1):")
    ranges_te = list(most_loaded.RainflowHalfCycles("Effective tension", period,
                                                     OrcFxAPI.oeEndA))
    print(f"    Half-cycles  : {len(ranges_te)}")
    if ranges_te:
        print(f"    Largest range: {max(ranges_te):.1f} kN  "
              f"(= {100*max(ranges_te)/mooring_mbl:.1f}% MBL)")

    return {
        "platform"      : platform,
        "cable"         : cable,
        "mooring_lines" : mooring_lines,
        "mooring_rg"    : mooring_rg,
        "rg_te_cable"   : rg_cable,
        "rg_curv_cable" : rg_curv,
        "most_loaded"   : most_loaded,
        "cfg"           : cfg,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Extreme-statistics aggregation across seeds
# ══════════════════════════════════════════════════════════════════════════════
def _aggregate_extremes(sim_paths, cfg):
    """Compute Rayleigh-fitted extremes for each seed; print summary."""
    period      = cfg["period"]
    storm_hours = cfg["storm_hours"]
    risk_pct    = cfg["risk_pct"]
    mooring_mbl = cfg["mooring_mbl"]

    SEP = "=" * 65
    print(f"\n{SEP}\nSECTION 7 — Extreme Statistics  "
          f"({storm_hours} h storm, {risk_pct}% risk, "
          f"{len(sim_paths)} seed{'s' if len(sim_paths) > 1 else ''})\n{SEP}")

    metrics = {"heave_mpm_up": [], "heave_mpm_lo": [],
               "moor_mpm":     [], "moor_risk":    [],
               "cable_mpm":    [], "cable_risk":   []}
    most_loaded_name = None

    for idx, sim_path in enumerate(sim_paths):
        m  = OrcFxAPI.Model(sim_path)
        pf = m["Platform"]
        cb = m["ExportCable"]
        mls = [o for o in m.objects if o.Name.startswith("Mooring")]
        # Pick the most-loaded line based on this seed's tension envelope
        most = max(mls, key=lambda ml:
                   float(np.max(ml.RangeGraph("Effective tension", period).Max)))
        if most_loaded_name is None:
            most_loaded_name = most.Name

        r_h = _rayleigh_extremes(pf, "Z", period, storm_hours, risk_pct)
        r_m = _rayleigh_extremes(most, "Effective tension", period, storm_hours,
                                 risk_pct, oe=OrcFxAPI.oeEndA)
        r_c = _rayleigh_extremes(cb, "Effective tension", period, storm_hours,
                                 risk_pct, oe=OrcFxAPI.oeEndA)
        metrics["heave_mpm_up"].append(r_h["upper"][0])
        metrics["heave_mpm_lo"].append(r_h["lower"][0])
        metrics["moor_mpm"].append(r_m["upper"][0])
        metrics["moor_risk"].append(r_m["upper"][1])
        metrics["cable_mpm"].append(r_c["upper"][0])
        metrics["cable_risk"].append(r_c["upper"][1])
        print(f"  seed {idx+1}/{len(sim_paths)}: "
              f"heave_max_MPM={r_h['upper'][0]:5.2f} m  "
              f"moor_max_MPM={r_m['upper'][0]:7.1f} kN  "
              f"cable_max_MPM={r_c['upper'][0]:6.1f} kN")

    def _stats(arr):
        a = np.asarray(arr)
        return a.mean(), a.std(), a.max()

    print("\n  Summary across seeds  (mean ± std, worst):")
    h_up = _stats(metrics["heave_mpm_up"])
    h_lo = _stats(metrics["heave_mpm_lo"])
    m_mp = _stats(metrics["moor_mpm"])
    m_rk = _stats(metrics["moor_risk"])
    c_mp = _stats(metrics["cable_mpm"])
    c_rk = _stats(metrics["cable_risk"])

    print(f"    Platform heave MPM max : {h_up[0]:6.2f} ± {h_up[1]:.2f} m  (worst {h_up[2]:.2f} m)")
    print(f"    Platform heave MPM min : {h_lo[0]:6.2f} ± {h_lo[1]:.2f} m  (worst {h_lo[2]:.2f} m)")
    print(f"    {most_loaded_name} tension at End A:")
    print(f"      MPM max          : {m_mp[0]:7.1f} ± {m_mp[1]:.1f} kN  "
          f"(worst {m_mp[2]:.1f} kN, UT = {100*m_mp[2]/mooring_mbl:.1f}% MBL)")
    print(f"      {risk_pct}% risk max     : {m_rk[0]:7.1f} ± {m_rk[1]:.1f} kN  "
          f"(worst {m_rk[2]:.1f} kN)")
    print(f"    Export cable tension at End A:")
    print(f"      MPM max          : {c_mp[0]:7.1f} ± {c_mp[1]:.1f} kN  (worst {c_mp[2]:.1f} kN)")
    print(f"      {risk_pct}% risk max     : {c_rk[0]:7.1f} ± {c_rk[1]:.1f} kN  (worst {c_rk[2]:.1f} kN)")

    print(f"\n{SEP}\nPost-processing complete.\n{SEP}")


# ══════════════════════════════════════════════════════════════════════════════
# Plotting (uses the first seed's results)
# ══════════════════════════════════════════════════════════════════════════════
def _plot_all(ctx, out_dir):
    cfg           = ctx["cfg"]
    period        = cfg["period"]
    mooring_mbl   = cfg["mooring_mbl"]
    cable_mbr     = cfg["cable_mbr"]
    platform      = ctx["platform"]
    mooring_lines = ctx["mooring_lines"]
    mooring_rg    = ctx["mooring_rg"]
    rg_te_cable   = ctx["rg_te_cable"]
    rg_curv_cable = ctx["rg_curv_cable"]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _mask_fpu_exceptions()  # matplotlib import unmasks FP exceptions on Windows

    # ── Figure 1: Platform 6-DOF time histories ──────────────────────────────
    t_arr = platform.SampleTimes(period)
    fig1, axes1 = plt.subplots(3, 2, figsize=(12, 9), sharex=True)
    fig1.suptitle("Platform 6-DOF Motions", fontsize=13, fontweight="bold")
    for ax, (label, var) in zip(axes1.flat, DOF_VARS):
        th = np.asarray(platform.TimeHistory(var, period))
        ax.plot(t_arr, th, lw=0.8, color="steelblue")
        ax.axhline(th.mean(), color="tomato", lw=1.2, ls="--",
                   label=f"mean={th.mean():.3f}")
        ax.set_ylabel(f"{label} ({DOF_UNITS[var]})", fontsize=9)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.3)
    for ax in axes1[-1]:
        ax.set_xlabel("Time (s)", fontsize=9)
    fig1.tight_layout()
    path1 = os.path.join(out_dir, "fig1_platform_motions.png")
    fig1.savefig(path1, dpi=150)
    plt.close(fig1)

    # ── Figure 2: Mooring tension envelopes ──────────────────────────────────
    fig2, axes2 = plt.subplots(len(mooring_lines), 1,
                                figsize=(10, 3.2 * len(mooring_lines)),
                                squeeze=False)
    fig2.suptitle("Mooring Tension Envelope", fontsize=13, fontweight="bold")
    for ax, ml in zip(axes2[:, 0], mooring_lines):
        rg = mooring_rg[ml.Name]
        ax.fill_between(rg.X, rg.Min, rg.Max, alpha=0.25, color="navy",
                        label="Min–Max envelope")
        ax.plot(rg.X, rg.Mean, color="navy", lw=1.4, label="Mean")
        ax.axhline(mooring_mbl, color="black", lw=1.0, ls=":",
                   label=f"MBL = {mooring_mbl:.0f} kN")
        ax.set_title(ml.Name, fontsize=10)
        ax.set_ylabel("Effective Tension (kN)", fontsize=9)
        ax.set_xlabel("Arc Length (m)", fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    fig2.tight_layout()
    path2 = os.path.join(out_dir, "fig2_mooring_tension.png")
    fig2.savefig(path2, dpi=150)
    plt.close(fig2)

    # ── Figure 3: Cable tension and curvature along arc length ──────────────
    fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    fig3.suptitle("Export Cable Along Arc Length", fontsize=13, fontweight="bold")

    ax3a.fill_between(rg_te_cable.X, rg_te_cable.Min, rg_te_cable.Max,
                      alpha=0.25, color="darkorange", label="Min–Max envelope")
    ax3a.plot(rg_te_cable.X, rg_te_cable.Mean, color="darkorange",
              lw=1.4, label="Mean")
    ax3a.set_ylabel("Effective Tension (kN)", fontsize=9)
    ax3a.legend(fontsize=8)
    ax3a.grid(True, alpha=0.3)

    ax3b.fill_between(rg_curv_cable.X, rg_curv_cable.Min, rg_curv_cable.Max,
                      alpha=0.25, color="purple", label="Min–Max envelope")
    ax3b.plot(rg_curv_cable.X, rg_curv_cable.Mean, color="purple",
              lw=1.4, label="Mean")
    ax3b.axhline(1.0 / cable_mbr, color="black", lw=1.0, ls=":",
                 label=f"1/MBR limit = {1/cable_mbr:.4f} rad/m")
    ax3b.set_ylabel("Curvature (rad/m)", fontsize=9)
    ax3b.set_xlabel("Arc Length (m)", fontsize=9)
    ax3b.legend(fontsize=8)
    ax3b.grid(True, alpha=0.3)

    fig3.tight_layout()
    path3 = os.path.join(out_dir, "fig3_cable_tension_curvature.png")
    fig3.savefig(path3, dpi=150)
    plt.close(fig3)

    return [path1, path2, path3]


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════
def post_process(sim_paths, params: dict, out_dir: str) -> dict:
    """Run post-processing on one or more .sim files.

    Returns a dict of artefact paths: {"report": ..., "figures": [...]}.
    """
    if isinstance(sim_paths, str):
        sim_paths = [sim_paths]
    p = params_with_defaults(params)
    cfg = {
        "period":      int(p["period"]),
        "mooring_mbl": float(p["mooring_mbl"]),
        "cable_mbr":   float(p["cable_mbr"]),
        "storm_hours": int(p["storm_hours"]),
        "risk_pct":    int(p["risk_pct"]),
    }

    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "results_report.txt")

    # Use the first seed for static / motions / fatigue sections and plots
    model = OrcFxAPI.Model(sim_paths[0])
    with open(report_path, "w", encoding="utf-8") as log:
        tee = _Tee(sys.stdout, log)
        with redirect_stdout(tee):
            ctx = _run_report(model, cfg)
            _aggregate_extremes(sim_paths, cfg)

    fig_paths = _plot_all(ctx, out_dir)

    print(f"Results written to: {report_path}")
    for p_ in fig_paths:
        print(f"Figure saved      : {p_}")

    return {"report": report_path, "figures": fig_paths}


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    sim_path = os.path.join(HERE, "testModel.sim")
    if not os.path.exists(sim_path):
        print(
            f"\nERROR — simulation file not found: {sim_path}\n"
            f"        Run workflow_02_run.py first to produce the .sim file.",
            file=sys.stderr,
        )
        sys.exit(1)
    post_process([sim_path], params_with_defaults(), out_dir=HERE)


if __name__ == "__main__":
    main()
