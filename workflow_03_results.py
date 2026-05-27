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
  7. Extreme statistics         (Rayleigh fits, MPM, risk-factor extremes)

Period selection quick reference
  PeriodNum.WholeSimulation   all stages
  0                           build-up ramp (stage 0)
  1                           analysis stage (stage 1) ← use for ULS / fatigue
  PeriodNum.LatestWave        last complete wave period
  SpecifiedPeriod(t1, t2)     explicit window in seconds

Outputs (written next to this script)
  results_report.txt              full text log
  fig1_platform_motions.png       6-DOF time histories
  fig2_mooring_tension.png        tension envelopes per leg
  fig3_cable_tension_curvature.png  cable tension + curvature along arc

Requires: workflow_02_run.py must have been run first (testModel.sim).
"""

import math
import os
import sys
from contextlib import redirect_stdout

import OrcFxAPI
import numpy as np
import matplotlib
matplotlib.use("Agg")   # non-interactive backend; switch to "TkAgg" to show windows
import matplotlib.pyplot as plt

from project_config import MOORING_MBL, CABLE_MBR

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
STORM_HOURS = 3          # h   storm duration for extreme statistics
RISK_PCT    = 5          # %   risk factor for extreme value query
PERIOD      = 1          # analysis stage (stage 1)

HERE       = os.path.dirname(os.path.abspath(__file__))
SIM_PATH   = os.path.join(HERE, "testModel.sim")
REPORT_TXT = os.path.join(HERE, "results_report.txt")


# ── Tee: mirror writes to console + file ─────────────────────────────────────
class _Tee:
    """Mirrors writes to two streams (console + log file)."""
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


def run_report(model):
    """Print the full text report (also mirrored to results_report.txt)."""
    platform = model["Platform"]
    cable    = model["ExportCable"]
    env      = model.environment

    water_depth = float(env.WaterDepth)

    # Collect all mooring line objects dynamically by name prefix
    mooring_lines = [obj for obj in model.objects if obj.Name.startswith("Mooring")]

    # Cache the mooring tension RangeGraphs — used by several sections
    mooring_rg = {ml.Name: ml.RangeGraph("Effective tension", PERIOD)
                  for ml in mooring_lines}

    print(f"Simulation loaded.  State: {model.state.name}")
    print(f"  Mooring lines found: {[ml.Name for ml in mooring_lines]}")
    print(f"  Water depth        : {water_depth:.1f} m")
    t = platform.SampleTimes(PERIOD)
    print(f"  Analysis window    : {t[0]:.1f} s – {t[-1]:.1f} s  ({len(t)} samples)")

    SEP = "=" * 65

    # =========================================================================
    # SECTION 1 — Static Equilibrium
    # =========================================================================
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

    # =========================================================================
    # SECTION 2 — Platform / Vessel Motions (6-DOF)
    # =========================================================================
    print(f"\n{SEP}\nSECTION 2 — Platform Motions  (stage 1)\n{SEP}")

    # NOTE: with a default VesselType (no RAOs / no wind & current drag), the
    # platform only moves through mooring + cable reactions in the wave-loaded
    # plane, so Sway / Roll / Yaw are identically zero.  Assign a real
    # VesselType in workflow_01 to get representative 6-DOF response.

    print(f"\n  {'DOF':<14}  {'Mean':>9}  {'Std':>9}  {'Min':>9}  {'Max':>9}  {'Range':>9}")
    for label, var in DOF_VARS:
        th = np.asarray(platform.TimeHistory(var, PERIOD))
        print(f"  {label:<14}  {th.mean():9.3f}  {th.std():9.3f}  "
              f"{th.min():9.3f}  {th.max():9.3f}  {np.ptp(th):9.3f}")

    elev = env.TimeHistory("Elevation", PERIOD, OrcFxAPI.oeEnvironment(0.0, 0.0, 0.0))
    print(f"\n  Measured Hs (4σ at origin) = {4*np.std(elev):.2f} m  "
          f"(target = {env.WaveHs:.2f} m)")

    # =========================================================================
    # SECTION 3 — Mooring System: Tension Envelope and Utilisation
    # =========================================================================
    print(f"\n{SEP}\nSECTION 3 — Mooring System  (stage 1)\n{SEP}")

    print(f"\n  MBL = {MOORING_MBL:.0f} kN")
    print(f"\n  {'Line':<12}  {'Te_max (kN)':>12}  {'UT_max (%)':>11}  "
          f"{'Arc of max (m)':>15}  {'Te_min (kN)':>12}")
    for ml in mooring_lines:
        rg = mooring_rg[ml.Name]
        idx_max = int(np.argmax(rg.Max))
        Te_max  = rg.Max[idx_max]
        UT_max  = 100.0 * Te_max / MOORING_MBL
        arc_max = rg.X[idx_max]
        Te_min  = float(np.min(rg.Min))
        print(f"  {ml.Name:<12}  {Te_max:12.1f}  {UT_max:10.1f}%  "
              f"{arc_max:15.1f}  {Te_min:12.1f}")

    # Linked statistics: tension at fairlead paired with platform X offset
    # (chain has EIx=EIy=0 → "Bend moment" is identically zero, so we pair Te
    #  with End-A X position to show the surge-correlated tension peak instead).
    print("\n  Linked statistics at fairlead (arc 0 m ≡ End A):")
    print(f"  {'Line':<12}  {'MaxTe (kN)':>12}  {'X@MaxTe (m)':>13}  {'t_max (s)':>10}")
    for ml in mooring_lines:
        ls = ml.LinkedStatistics(("Effective tension", "X"), PERIOD, OrcFxAPI.oeEndA)
        q  = ls.Query("Effective tension", "X")
        print(f"  {ml.Name:<12}  {q.ValueAtMax:12.1f}  {q.LinkedValueAtMax:13.2f}  "
              f"{q.TimeOfMax:10.2f}")

    # =========================================================================
    # SECTION 4 — Dynamic Export Cable
    # =========================================================================
    print(f"\n{SEP}\nSECTION 4 — Dynamic Export Cable  (stage 1)\n{SEP}")

    rg_cable = cable.RangeGraph("Effective tension", PERIOD)
    idx_max  = int(np.argmax(rg_cable.Max))
    print("\n  Tension envelope:")
    print(f"    Peak max tension : {rg_cable.Max[idx_max]:.1f} kN  "
          f"at arc = {rg_cable.X[idx_max]:.1f} m")
    print(f"    Global min tension: {float(np.min(rg_cable.Min)):.1f} kN")

    # Minimum bend radius along the cable (MBR = 1 / max curvature)
    rg_curv  = cable.RangeGraph("Curvature", PERIOD)
    max_curv = float(np.max(rg_curv.Max))
    mbr_dynamic = 1.0 / max_curv
    arc_mbr     = rg_curv.X[int(np.argmax(rg_curv.Max))]
    flag        = "FAIL ✗" if mbr_dynamic < CABLE_MBR else "PASS ✓"
    print(f"\n  Minimum dynamic bend radius : {mbr_dynamic:.2f} m  "
          f"(limit = {CABLE_MBR:.2f} m)  [{flag}]  at arc = {arc_mbr:.1f} m")

    # Touchdown point — first arc length (scanning from hang-off) where the
    # mean Z reaches the seabed (within tolerance).
    rg_z   = cable.RangeGraph("Z", PERIOD)
    z_tol  = 1.0   # m
    seabed = -water_depth
    tdp_arc = next((x for x, z in zip(rg_z.X, rg_z.Mean) if z <= seabed + z_tol),
                   None)
    if tdp_arc is None:
        print("\n  Touchdown point not detected (cable does not reach seabed).")
    else:
        print(f"\n  Approximate TDP arc length  : {tdp_arc:.1f} m")

    # =========================================================================
    # SECTION 5 — Linked Statistics and Spectral Moments (cable mid-buoyancy)
    # =========================================================================
    print(f"\n{SEP}\nSECTION 5 — Linked Statistics (cable at mid-buoyancy section)\n{SEP}")

    # Read section lengths from the model — no hard-coded geometry.
    section_lengths = list(cable.Length)
    arc_mid = sum(section_lengths[:1]) + section_lengths[1] / 2.0
    oe_mid  = OrcFxAPI.oeArcLength(arc_mid)

    ls_cable = cable.LinkedStatistics(
        ("Effective tension", "Bend moment"), PERIOD, oe_mid
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

    # =========================================================================
    # SECTION 6 — Fatigue: Rainflow Half-Cycles
    # =========================================================================
    print(f"\n{SEP}\nSECTION 6 — Fatigue: Rainflow Half-Cycles\n{SEP}")

    print("\n  Platform heave rainflow (stage 1):")
    ranges_z = list(platform.RainflowHalfCycles("Z", PERIOD))
    print(f"    Half-cycles  : {len(ranges_z)}")
    if ranges_z:
        print(f"    Largest range: {max(ranges_z):.3f} m")
        bins = np.linspace(0.0, max(ranges_z), 7)
        counts, _ = np.histogram(ranges_z, bins=bins)
        for i, c in enumerate(counts):
            print(f"    [{bins[i]:.2f} – {bins[i+1]:.2f} m]  {c:>5} half-cycles")

    # Most-loaded line — chosen from the cached range graphs (no recomputation)
    most_loaded = max(mooring_lines,
                      key=lambda ml: float(np.max(mooring_rg[ml.Name].Max)))
    print(f"\n  Mooring tension rainflow — {most_loaded.Name} at End A (stage 1):")
    ranges_te = list(most_loaded.RainflowHalfCycles("Effective tension", PERIOD,
                                                     OrcFxAPI.oeEndA))
    print(f"    Half-cycles  : {len(ranges_te)}")
    if ranges_te:
        print(f"    Largest range: {max(ranges_te):.1f} kN  "
              f"(= {100*max(ranges_te)/MOORING_MBL:.1f}% MBL)")

    # =========================================================================
    # SECTION 7 — Extreme Statistics
    # =========================================================================
    print(f"\n{SEP}\nSECTION 7 — Extreme Statistics  "
          f"({STORM_HOURS} h storm, {RISK_PCT}% risk)\n{SEP}")

    print("\n  Platform heave (Z):")
    r_heave = _rayleigh_extremes(platform, "Z", PERIOD)
    print(f"    MPM max heave : {r_heave['upper'][0]:.2f} m  "
          f"({RISK_PCT}% risk max: {r_heave['upper'][1]:.2f} m)")
    print(f"    MPM min heave : {r_heave['lower'][0]:.2f} m  "
          f"({RISK_PCT}% risk min: {r_heave['lower'][1]:.2f} m)")

    print(f"\n  {most_loaded.Name} tension at End A:")
    r_moor = _rayleigh_extremes(most_loaded, "Effective tension", PERIOD,
                                 oe=OrcFxAPI.oeEndA)
    UT_extreme = 100.0 * r_moor["upper"][0] / MOORING_MBL
    print(f"    MPM max tension: {r_moor['upper'][0]:.1f} kN  "
          f"(UT = {UT_extreme:.1f}% of MBL = {MOORING_MBL:.0f} kN)")
    print(f"    {RISK_PCT}% risk max   : {r_moor['upper'][1]:.1f} kN")

    print("\n  Export cable tension at hang-off (End A):")
    r_cable = _rayleigh_extremes(cable, "Effective tension", PERIOD,
                                  oe=OrcFxAPI.oeEndA)
    print(f"    MPM max tension: {r_cable['upper'][0]:.1f} kN")
    print(f"    {RISK_PCT}% risk max   : {r_cable['upper'][1]:.1f} kN")

    print(f"\n{SEP}\nPost-processing complete.\n{SEP}")

    return {
        "platform"      : platform,
        "cable"         : cable,
        "mooring_lines" : mooring_lines,
        "mooring_rg"    : mooring_rg,
        "rg_te_cable"   : rg_cable,
        "rg_curv_cable" : rg_curv,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
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


def _rayleigh_extremes(obj, var_name, period, oe=None):
    """Return {'upper': (MPM, risk_value), 'lower': (MPM, risk_value)}."""
    kwargs = {"objectExtra": oe} if oe is not None else {}
    ext    = obj.ExtremeStatistics(var_name, period, **kwargs)
    out    = {}
    for label, tail in [("upper", OrcFxAPI.DistributionTail.Upper),
                        ("lower", OrcFxAPI.DistributionTail.Lower)]:
        ext.Fit(OrcFxAPI.RayleighStatisticsSpecification(tail))
        r = ext.Query(OrcFxAPI.RayleighStatisticsQuery(STORM_HOURS, RISK_PCT))
        out[label] = (r.MostProbableExtremeValue, r.ExtremeValueWithRiskFactor)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PLOTTING
# ══════════════════════════════════════════════════════════════════════════════
def plot_all(ctx):
    """Generate and save all figures.  ctx = dict returned by run_report."""
    platform      = ctx["platform"]
    cable         = ctx["cable"]
    mooring_lines = ctx["mooring_lines"]
    mooring_rg    = ctx["mooring_rg"]
    rg_te_cable   = ctx["rg_te_cable"]
    rg_curv_cable = ctx["rg_curv_cable"]

    # ── Figure 1: Platform 6-DOF time histories ──────────────────────────────
    t_arr = platform.SampleTimes(PERIOD)

    fig1, axes1 = plt.subplots(3, 2, figsize=(12, 9), sharex=True)
    fig1.suptitle("Platform 6-DOF Motions  (stage 1)", fontsize=13, fontweight="bold")
    for ax, (label, var) in zip(axes1.flat, DOF_VARS):
        th = np.asarray(platform.TimeHistory(var, PERIOD))
        ax.plot(t_arr, th, lw=0.8, color="steelblue")
        ax.axhline(th.mean(), color="tomato", lw=1.2, ls="--",
                   label=f"mean={th.mean():.3f}")
        ax.set_ylabel(f"{label} ({DOF_UNITS[var]})", fontsize=9)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.3)
    for ax in axes1[-1]:
        ax.set_xlabel("Time (s)", fontsize=9)
    fig1.tight_layout()
    path1 = os.path.join(HERE, "fig1_platform_motions.png")
    fig1.savefig(path1, dpi=150)
    plt.close(fig1)
    print(f"Figure 1 saved: {path1}")

    # ── Figure 2: Mooring tension envelopes ──────────────────────────────────
    fig2, axes2 = plt.subplots(len(mooring_lines), 1,
                                figsize=(10, 3.2 * len(mooring_lines)),
                                squeeze=False)
    fig2.suptitle("Mooring Tension Envelope  (stage 1)",
                  fontsize=13, fontweight="bold")
    for ax, ml in zip(axes2[:, 0], mooring_lines):
        rg = mooring_rg[ml.Name]
        ax.fill_between(rg.X, rg.Min, rg.Max, alpha=0.25, color="navy",
                        label="Min–Max envelope")
        ax.plot(rg.X, rg.Mean, color="navy", lw=1.4, label="Mean")
        ax.axhline(MOORING_MBL, color="black", lw=1.0, ls=":",
                   label=f"MBL = {MOORING_MBL:.0f} kN")
        ax.set_title(ml.Name, fontsize=10)
        ax.set_ylabel("Effective Tension (kN)", fontsize=9)
        ax.set_xlabel("Arc Length (m)", fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    fig2.tight_layout()
    path2 = os.path.join(HERE, "fig2_mooring_tension.png")
    fig2.savefig(path2, dpi=150)
    plt.close(fig2)
    print(f"Figure 2 saved: {path2}")

    # ── Figure 3: Cable tension and curvature along arc length ──────────────
    fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    fig3.suptitle("Export Cable Along Arc Length  (stage 1)",
                  fontsize=13, fontweight="bold")

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
    ax3b.axhline(1.0 / CABLE_MBR, color="black", lw=1.0, ls=":",
                 label=f"1/MBR limit = {1/CABLE_MBR:.4f} rad/m")
    ax3b.set_ylabel("Curvature (rad/m)", fontsize=9)
    ax3b.set_xlabel("Arc Length (m)", fontsize=9)
    ax3b.legend(fontsize=8)
    ax3b.grid(True, alpha=0.3)

    fig3.tight_layout()
    path3 = os.path.join(HERE, "fig3_cable_tension_curvature.png")
    fig3.savefig(path3, dpi=150)
    plt.close(fig3)
    print(f"Figure 3 saved: {path3}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    model = OrcFxAPI.Model(SIM_PATH)

    # Write text report (mirrored to console + file) using a guaranteed restore.
    with open(REPORT_TXT, "w", encoding="utf-8") as log:
        tee = _Tee(sys.stdout, log)
        with redirect_stdout(tee):
            ctx = run_report(model)

    print(f"Results written to: {REPORT_TXT}")
    plot_all(ctx)


if __name__ == "__main__":
    main()
