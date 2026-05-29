"""
OrcaFlex FOWT Analysis — Streamlit GUI
=======================================
Drives workflow_01_build → workflow_02_run → workflow_03_results in-process.

Design notes
------------
• All workflow scripts expose a Python function (build / run / post_process);
  the GUI calls them directly inside the Streamlit process. No subprocesses,
  no environment variables, no on-disk mutation of project_config.py.
  → first-step progress is updated *between* phases, not all at once.
  → no per-call Python startup + OrcFxAPI DLL load overhead.

• Output caching: every parameter set hashes to a unique sub-directory under
  ./runs/. Re-running with the same parameters reuses the cached artefacts.

• To add a new input parameter:
    1. Add a default in project_config.GUI_DEFAULTS.
    2. Add a widget below using `value=D["<key>"]`.
    3. Add the key to the `params` dict in the run block.
    4. Read it inside the relevant workflow function — that's it.
"""

import io
import math
import os
from contextlib import redirect_stdout

import streamlit as st

from project_config import GUI_DEFAULTS as D, MOORING_HEADINGS, params_hash
from workflow_01_build  import build
from workflow_02_run    import run as run_sims
from workflow_03_results import post_process

HERE     = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(HERE, "runs")


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OrcaFlex FOWT Analysis",
    page_icon="🌊",
    layout="wide",
)

st.title("🌊 OrcaFlex FOWT Analysis")
st.caption("Semi-submersible platform · Catenary mooring · Lazy-wave export cable")


# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR — all input parameters grouped by category
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Input Parameters")

    st.warning(
        "**Modelling assumption:** the Platform uses the OrcaFlex *default* "
        "VesselType (no RAOs, no diffraction, no wind/current drag). "
        "Sway / Roll / Yaw will read as zero. For a representative FOWT, "
        "import a project-specific VesselType (RAOs + QTFs from WAMIT/AQWA).",
        icon="⚠️",
    )

    with st.expander("🏔️ Site", expanded=True):
        water_depth = st.number_input(
            "Water Depth (m)", value=D["water_depth"], min_value=50.0, max_value=3000.0, step=10.0
        )

    with st.expander("🌊 Sea State (ULS / 50-yr)", expanded=True):
        wave_hs        = st.number_input("Hs — Significant Wave Height (m)",  value=D["wave_hs"],        min_value=0.5,   max_value=25.0,  step=0.5)
        wave_tp        = st.number_input("Tp — Spectral Peak Period (s)",     value=D["wave_tp"],        min_value=3.0,   max_value=30.0,  step=0.5)
        wave_direction = st.number_input("Wave Direction (deg)",              value=D["wave_direction"], min_value=0.0,   max_value=360.0, step=15.0)

    with st.expander("💨 Wind"):
        wind_speed     = st.number_input("Wind Speed — 10-min mean (m/s)",   value=D["wind_speed"],     min_value=0.0, max_value=70.0,  step=1.0)
        wind_direction = st.number_input("Wind Direction (deg)",             value=D["wind_direction"], min_value=0.0, max_value=360.0, step=15.0)

    with st.expander("🌀 Current"):
        current_speed = st.number_input("Current Speed — surface (m/s)",    value=D["current_speed"], min_value=0.0, max_value=5.0,   step=0.1)
        current_dir   = st.number_input("Current Direction (deg)",          value=D["current_dir"],   min_value=0.0, max_value=360.0, step=15.0)

    with st.expander("⚓ Mooring System"):
        mooring_mbl    = st.number_input("MBL — Min. Breaking Load (kN)",   value=D["mooring_mbl"],     min_value=1000.0, max_value=50000.0, step=100.0)
        fairlead_radius= st.number_input("Fairlead Radius (m)",             value=D["fairlead_radius"], min_value=10.0,   max_value=100.0,   step=1.0)
        fairlead_depth = st.number_input("Fairlead Depth below WL (m, −ve)",value=D["fairlead_depth"],  min_value=-60.0,  max_value=0.0,     step=1.0)
        anchor_radius  = st.number_input("Anchor Radius (m)",               value=D["anchor_radius"],   min_value=100.0,  max_value=2000.0,  step=10.0)
        mooring_length = st.number_input("Chain Length per Leg (m)",        value=D["mooring_length"],  min_value=100.0,  max_value=3000.0,  step=10.0)
        st.caption("Per-line orientation & statics")
        _m_tabs = st.tabs([f"Mooring {i+1} ({h:.0f}°)" for i, h in enumerate(MOORING_HEADINGS)])
        mooring_per_line = []
        for _mi, (_tab, _hdg) in enumerate(zip(_m_tabs, MOORING_HEADINGS), start=1):
            with _tab:
                st.caption("End A (fairlead) orientation")
                _enda_az  = st.number_input("End A Azimuth (deg)",     value=_hdg,                          min_value=0.0,    max_value=360.0, step=15.0, key=f"m{_mi}_enda_az")
                _enda_dec = st.number_input("End A Declination (deg)", value=D["mooring_enda_declination"], min_value=-90.0,  max_value=90.0,  step=5.0,  key=f"m{_mi}_enda_dec",
                                            help="0 = horizontal connection at fairlead")
                _enda_gam = st.number_input("End A Gamma (deg)",       value=D["mooring_enda_gamma"],       min_value=-180.0, max_value=180.0, step=5.0,  key=f"m{_mi}_enda_gam")
                st.caption("End B (anchor) orientation")
                _endb_az  = st.number_input("End B Azimuth (deg)",     value=_hdg,                          min_value=0.0,    max_value=360.0, step=15.0, key=f"m{_mi}_endb_az")
                _endb_dec = st.number_input("End B Declination (deg)", value=D["mooring_endb_declination"], min_value=-90.0,  max_value=90.0,  step=5.0,  key=f"m{_mi}_endb_dec",
                                            help="90 = vertical at anchor")
                _endb_gam = st.number_input("End B Gamma (deg)",       value=D["mooring_endb_gamma"],       min_value=-180.0, max_value=180.0, step=5.0,  key=f"m{_mi}_endb_gam")
                st.caption("Statics")
                _lay_az_default = (_hdg + 180.0 + D["mooring_lay_azimuth_off"]) % 360.0
                _lay_az   = st.number_input("Lay Azimuth (deg)",       value=_lay_az_default,                min_value=0.0,    max_value=360.0,  step=15.0, key=f"m{_mi}_lay_az")
                _as_laid  = st.number_input("As-Laid Tension (kN)",    value=D["mooring_as_laid_tension"],   min_value=0.0,    max_value=5000.0, step=10.0, key=f"m{_mi}_as_laid",
                                            help="0 = OrcaFlex calculates from geometry")
                mooring_per_line.append(dict(
                    enda_azimuth=_enda_az, enda_declination=_enda_dec, enda_gamma=_enda_gam,
                    endb_azimuth=_endb_az, endb_declination=_endb_dec, endb_gamma=_endb_gam,
                    lay_azimuth=_lay_az, as_laid_tension=_as_laid,
                ))

    with st.expander("🔌 Dynamic Export Cable"):
        cable_mbr      = st.number_input("MBR — Min. Allowable Bend Radius (m)", value=D["cable_mbr"],        min_value=0.5,     max_value=10.0,   step=0.1)
        cable_hangoff_x= st.number_input("Hang-off X (m)",                       value=D["cable_hangoff_x"],  min_value=-200.0,  max_value=0.0,    step=5.0)
        cable_hangoff_z= st.number_input("Hang-off Depth below WL (m, −ve)",     value=D["cable_hangoff_z"],  min_value=-60.0,   max_value=0.0,    step=1.0)
        cable_seabed_x = st.number_input("J-tube X on Seabed (m)",               value=D["cable_seabed_x"],   min_value=-2000.0, max_value=0.0,    step=10.0)
        st.caption("End A (hang-off / I-tube) orientation")
        cable_enda_azimuth     = st.number_input("End A Azimuth (deg)",     value=D["cable_enda_azimuth"],     min_value=0.0,    max_value=360.0, step=15.0, key="cab_enda_az")
        cable_enda_declination = st.number_input("End A Declination (deg)", value=D["cable_enda_declination"], min_value=-90.0,  max_value=90.0,  step=5.0,  key="cab_enda_dec",
                                                 help="0 = horizontal I-tube exit")
        cable_enda_gamma       = st.number_input("End A Gamma (deg)",       value=D["cable_enda_gamma"],       min_value=-180.0, max_value=180.0, step=5.0,  key="cab_enda_gam")
        st.caption("End B (J-tube / seabed) orientation")
        cable_endb_azimuth     = st.number_input("End B Azimuth (deg)",     value=D["cable_endb_azimuth"],     min_value=0.0,    max_value=360.0, step=15.0, key="cab_endb_az")
        cable_endb_declination = st.number_input("End B Declination (deg)", value=D["cable_endb_declination"], min_value=-90.0,  max_value=90.0,  step=5.0,  key="cab_endb_dec",
                                                 help="90 = vertical entry into J-tube")
        cable_endb_gamma       = st.number_input("End B Gamma (deg)",       value=D["cable_endb_gamma"],       min_value=-180.0, max_value=180.0, step=5.0,  key="cab_endb_gam")
        st.caption("Statics")
        cable_lay_azimuth     = st.number_input("Lay Azimuth (deg)",       value=D["cable_lay_azimuth"],       min_value=0.0,    max_value=360.0,  step=15.0, key="cab_lay_az",
                                                help="Initial lay direction toward seabed J-tube")
        cable_as_laid_tension = st.number_input("As-Laid Tension (kN)",    value=D["cable_as_laid_tension"],   min_value=0.0,    max_value=5000.0, step=10.0, key="cab_as_laid",
                                                help="0 = OrcaFlex calculates from geometry")

    with st.expander("⏱️ Analysis Durations"):
        buildup_duration  = st.number_input("Build-up Duration (s)",        value=D["buildup_duration"],  min_value=10.0,  max_value=300.0,  step=10.0)
        analysis_duration = st.number_input("Analysis Duration (s)",        value=D["analysis_duration"], min_value=600.0, max_value=10800.0,step=600.0,
                                            help="1 h = 3600 s for ULS; use ≥ 10800 s (3 h) for fatigue")

    with st.expander("🎲 Random Seeds"):
        wave_seed = st.number_input("Base Wave Seed",     value=int(D["wave_seed"]), min_value=1, max_value=10**9, step=1)
        n_seeds   = st.number_input("Number of Seeds",    value=int(D["n_seeds"]),   min_value=1, max_value=50,    step=1,
                                    help="Run N independent simulations (seed_i = base + i). "
                                         "Extreme stats are aggregated; plots use seed 0. "
                                         "N ≥ 3 for screening, N ≥ 6 for Gumbel fit stability, "
                                         "N = 10–20 for design-grade ULS reports (DNV-RP-F205).")

    with st.expander("📈 Post-Processing"):
        storm_hours = st.number_input("Storm Duration (h) — extreme stats", value=int(D["storm_hours"]), min_value=1, max_value=24,  step=1)
        risk_pct    = st.number_input("Risk Factor (%) — extreme query",    value=int(D["risk_pct"]),    min_value=1, max_value=50,  step=1)
        period      = st.selectbox("Analysis Period (stage)", options=[0, 1], index=int(D["period"]),
                                   format_func=lambda i: f"Stage {i} ({'build-up' if i == 0 else 'analysis'})")
        analysis_mode = st.selectbox(
            "Design-Check Mode",
            options=["inplace", "marine_ops"],
            index=0 if D["analysis_mode"] == "inplace" else 1,
            format_func=lambda m: (
                "In-place  — DNVGL-OS-E301 / RP-F205 (P90, γ_mean / γ_dyn)"
                if m == "inplace"
                else "Marine Ops — DNV-ST-N001 / RP-H103 (P50/α or P90, γ_F = 1.30)"
            ),
            help=("In-place: permanent FOWT, characteristic load = T_P90. "
                  "Marine Ops: temporary phase; constrained = T_P50/α from "
                  "forecast, unconstrained = T_P90 from N-yr extreme sea state."),
        )

        # ── Mode-specific partial factors ─────────────────────────────────
        if analysis_mode == "inplace":
            cclass = st.selectbox(
                "Consequence Class (OS-E301 Table 2-3)",
                options=["class1", "class2"],
                index=0 if D["inplace_consequence_class"] == "class1" else 1,
                format_func=lambda c: (
                    "Class 1 — γ_mean = 1.40, γ_dyn = 1.70"
                    if c == "class1"
                    else "Class 2 — γ_mean = 1.75, γ_dyn = 2.20"
                ),
            )
            _defaults = {"class1": (1.40, 1.70), "class2": (1.75, 2.20)}
            _gm_d, _gd_d = _defaults[cclass]
            inplace_gamma_mean = st.number_input("γ_mean (override)", value=_gm_d,
                                                 min_value=1.00, max_value=3.00, step=0.05)
            inplace_gamma_dyn  = st.number_input("γ_dyn  (override)", value=_gd_d,
                                                 min_value=1.00, max_value=3.00, step=0.05)
            inplace_consequence_class = cclass
            # marine-ops fields keep defaults so cfg is always complete
            mo_weather_mode        = D["mo_weather_mode"]
            mo_gamma_f             = float(D["mo_gamma_f"])
            alpha_factor           = float(D["alpha_factor"])
            t_pop_hours            = float(D["t_pop_hours"])
            mo_return_period_years = int(D["mo_return_period_years"])
        else:
            mo_weather_mode = st.selectbox(
                "Weather Mode (ST-N001 §3.3)",
                options=["constrained", "unconstrained"],
                index=0 if D["mo_weather_mode"] == "constrained" else 1,
                format_func=lambda w: (
                    "Weather-constrained — forecast + α-factor (T_pop ≤ ref. period)"
                    if w == "constrained"
                    else "Weather-unconstrained — N-yr extreme sea state, no α"
                ),
                help=("Constrained: short ops planned to a weather window; "
                      "α-factor down-scales the forecast Hs. "
                      "Unconstrained: long ops (typically T_pop > 72 h) "
                      "designed for the N-year return-period sea state."),
            )
            mo_gamma_f = st.number_input("γ_F (ST-N001 load factor)",
                                         value=float(D["mo_gamma_f"]),
                                         min_value=1.00, max_value=2.00, step=0.05)
            if mo_weather_mode == "constrained":
                alpha_factor = st.number_input("α-factor (ST-N001 Table 4-3)",
                                               value=float(D["alpha_factor"]),
                                               min_value=0.50, max_value=1.00, step=0.05)
                t_pop_hours  = st.number_input("Planned operation T_pop (h)",
                                               value=float(D["t_pop_hours"]),
                                               min_value=1.0, max_value=240.0, step=1.0)
                mo_return_period_years = int(D["mo_return_period_years"])
            else:
                mo_return_period_years = st.selectbox(
                    "Design return period (yr)",
                    options=[1, 10, 100],
                    index=[1, 10, 100].index(int(D["mo_return_period_years"]))
                          if int(D["mo_return_period_years"]) in (1, 10, 100) else 1,
                    help=("1 yr seasonal: T_pop ≤ 72 h unconstrained. "
                          "10 yr: longer ops. 100 yr: in-place-equivalent."),
                )
                alpha_factor = float(D["alpha_factor"])
                t_pop_hours  = float(D["t_pop_hours"])
            # in-place fields keep defaults so cfg is always complete
            inplace_consequence_class = D["inplace_consequence_class"]
            inplace_gamma_mean        = float(D["inplace_gamma_mean"])
            inplace_gamma_dyn         = float(D["inplace_gamma_dyn"])

    st.divider()
    st.markdown("**Run pipeline step-by-step**")
    _step1_done = st.session_state.get("step1_done", False)
    _step2_done = st.session_state.get("step2_done", False)
    build_btn = st.button("1️⃣  Build Model",        type="primary",   use_container_width=True)
    run_btn   = st.button("2️⃣  Run Simulations",    type="primary",   use_container_width=True, disabled=not _step1_done)
    post_btn  = st.button("3️⃣  Post-process",       type="primary",   use_container_width=True, disabled=not _step2_done)
    st.markdown("**— or —**")
    all_btn   = st.button("▶  Run All (1 → 2 → 3)", type="primary",   use_container_width=True)
    reset_btn = st.button("🔄  Reset Pipeline",                          use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═════════════════════════════════════════════════════════════════════════════
def validate(params: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errs:  list[str] = []
    warns: list[str] = []

    # Geometric feasibility of the mooring catenary
    horiz = params["anchor_radius"] - params["fairlead_radius"]
    vert  = params["water_depth"] + params["fairlead_depth"]
    straight = math.hypot(horiz, vert)
    if params["mooring_length"] < straight:
        errs.append(
            f"Chain length per leg ({params['mooring_length']:.0f} m) is shorter than "
            f"the straight-line fairlead→anchor distance ({straight:.0f} m)."
        )

    if params["buildup_duration"] < 2 * params["wave_tp"]:
        errs.append(
            f"Build-up ({params['buildup_duration']:.0f} s) < 2·Tp "
            f"({2*params['wave_tp']:.1f} s) — ramp won't settle."
        )

    if params["cable_hangoff_z"] < -params["water_depth"]:
        errs.append("Cable hang-off Z is below the seabed.")

    if params["fairlead_depth"] < -params["water_depth"]:
        errs.append("Fairlead depth is below the seabed.")

    # Hs / Tp wave-steepness sanity (deep-water JONSWAP: 1.6√Hs ≤ Tp ≤ 6√Hs)
    tp_min = 1.6 * math.sqrt(params["wave_hs"])
    tp_max = 6.0 * math.sqrt(params["wave_hs"])
    if params["wave_tp"] < tp_min:
        warns.append(
            f"Tp ({params['wave_tp']:.1f} s) < 1.6·√Hs ({tp_min:.1f} s): "
            f"wave is steep — may break in deep water."
        )
    elif params["wave_tp"] > tp_max:
        warns.append(
            f"Tp ({params['wave_tp']:.1f} s) > 6·√Hs ({tp_max:.1f} s): swell-like, "
            f"unusual for a ULS design sea-state."
        )

    # Analysis duration vs storm window for extreme stats
    if params["analysis_duration"] < 1800.0:
        warns.append(
            f"Analysis duration ({params['analysis_duration']:.0f} s) < 30 min — "
            f"Rayleigh MPM extreme-stats estimates will be noisy; increase to ≥3 h "
            f"or use more seeds."
        )

    if params["n_seeds"] < 3:
        warns.append(
            f"n_seeds = {int(params['n_seeds'])}. "
            f"3–5 seeds recommended for stable extreme-value statistics."
        )

    # Environmental direction sanity
    spread = max(params["wave_direction"], params["wind_direction"], params["current_dir"]) \
           - min(params["wave_direction"], params["wind_direction"], params["current_dir"])
    if spread > 90.0:
        warns.append(
            f"Wave / wind / current directions span {spread:.0f}°. "
            f"Verify this matches your design metocean condition."
        )

    return errs, warns


# ═════════════════════════════════════════════════════════════════════════════
# RUNNER — one function per pipeline step
# ═════════════════════════════════════════════════════════════════════════════
def _expected_outputs(out_dir: str) -> list[str]:
    return [os.path.join(out_dir, f) for f in (
        "results_report.txt",
        "fig1_platform_motions.png",
        "fig2_mooring_tension.png",
        "fig3_cable_tension_curvature.png",
    )]


def step_build(params: dict, out_dir: str, log_box):
    """Step 1 — build OrcaFlex model. Returns (model, log)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        model = build(params)
    log_box.code(buf.getvalue() or "(no output)", language="bash")
    return model, buf.getvalue()


def step_run(params: dict, model, out_dir: str, log_box):
    """Step 2 — static + dynamic simulations. Returns (sim_paths, log)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        sim_paths = run_sims(params, out_dir=out_dir, model=model)
    log_box.code(buf.getvalue() or "(no output)", language="bash")
    return sim_paths, buf.getvalue()


def step_post(params: dict, sim_paths, out_dir: str, log_box):
    """Step 3 — post-processing. Returns log."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        post_process(sim_paths, params, out_dir=out_dir)
    log_box.code(buf.getvalue() or "(no output)", language="bash")
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN AREA — run + results
# ═════════════════════════════════════════════════════════════════════════════
for _k, _v in (("out_dir", None), ("analysis_log", ""),
               ("step1_done", False), ("step2_done", False),
               ("model", None), ("sim_paths", None), ("params", None)):
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _collect_params() -> dict:
    return dict(
        water_depth=water_depth,
        wave_hs=wave_hs, wave_tp=wave_tp, wave_direction=wave_direction,
        wind_speed=wind_speed, wind_direction=wind_direction,
        current_speed=current_speed, current_dir=current_dir,
        mooring_mbl=mooring_mbl, fairlead_radius=fairlead_radius,
        fairlead_depth=fairlead_depth, anchor_radius=anchor_radius,
        mooring_length=mooring_length,
        mooring_per_line=mooring_per_line,
        cable_mbr=cable_mbr, cable_hangoff_x=cable_hangoff_x,
        cable_hangoff_z=cable_hangoff_z, cable_seabed_x=cable_seabed_x,
        cable_enda_azimuth=cable_enda_azimuth,
        cable_enda_declination=cable_enda_declination,
        cable_enda_gamma=cable_enda_gamma,
        cable_endb_azimuth=cable_endb_azimuth,
        cable_endb_declination=cable_endb_declination,
        cable_endb_gamma=cable_endb_gamma,
        cable_lay_azimuth=cable_lay_azimuth,
        cable_as_laid_tension=cable_as_laid_tension,
        buildup_duration=buildup_duration, analysis_duration=analysis_duration,
        storm_hours=storm_hours, risk_pct=risk_pct, period=period,
        wave_seed=int(wave_seed), n_seeds=int(n_seeds),
        analysis_mode=analysis_mode,
        inplace_consequence_class=inplace_consequence_class,
        inplace_gamma_mean=float(inplace_gamma_mean),
        inplace_gamma_dyn=float(inplace_gamma_dyn),
        mo_weather_mode=mo_weather_mode,
        mo_gamma_f=float(mo_gamma_f),
        alpha_factor=float(alpha_factor),
        t_pop_hours=float(t_pop_hours),
        mo_return_period_years=int(mo_return_period_years),
    )


def _reset_pipeline():
    st.session_state.step1_done = False
    st.session_state.step2_done = False
    st.session_state.model = None
    st.session_state.sim_paths = None
    st.session_state.params = None
    st.session_state.analysis_log = ""


if reset_btn:
    _reset_pipeline()
    st.session_state.out_dir = None
    st.info("Pipeline state cleared. Start again from step 1.", icon="🔄")

# ── STEP 1 — BUILD ───────────────────────────────────────────────────────────
if build_btn:
    params = _collect_params()
    errors, warnings = validate(params)
    if errors:
        st.error("Please fix the following input errors before running:")
        for m in errors:
            st.markdown(f"- {m}")
        st.stop()
    for w in warnings:
        st.warning(w, icon="⚠️")

    cache_id = params_hash(params)
    out_dir  = os.path.join(RUNS_DIR, cache_id)
    os.makedirs(out_dir, exist_ok=True)

    # Cache short-circuit: if every artefact already exists, jump straight to
    # results without re-running any step.
    if all(os.path.exists(f) for f in _expected_outputs(out_dir)):
        st.session_state.params = params
        st.session_state.out_dir = out_dir
        st.session_state.step1_done = True
        st.session_state.step2_done = True
        st.session_state.analysis_log = f"♻️ Cache hit — reused runs/{cache_id}/\n"
        st.success(f"♻️ Cache hit — reusing `runs/{cache_id}/`. All three steps "
                   f"already complete; results shown below.")
    else:
        _reset_pipeline()
        st.session_state.params = params
        st.session_state.out_dir = out_dir
        with st.status("Step 1/3 — Building model…", expanded=True) as status:
            log_box = st.empty()
            try:
                model, log = step_build(params, out_dir, log_box)
                st.session_state.model = model
                st.session_state.analysis_log = log
                st.session_state.step1_done = True
                status.update(label="✅ Step 1/3 — Model built",
                              state="complete", expanded=False)
            except Exception as exc:
                st.session_state.analysis_log = f"ERROR (build): {exc}"
                status.update(label=f"❌ Step 1/3 failed: {exc}", state="error")

# ── STEP 2 — RUN SIMULATIONS ─────────────────────────────────────────────────
elif run_btn:
    if st.session_state.model is None or st.session_state.params is None:
        st.error("Run step 1 (Build Model) first.")
        st.stop()
    params  = st.session_state.params
    out_dir = st.session_state.out_dir
    n       = int(params["n_seeds"])
    with st.status(f"Step 2/3 — Running {n} simulation(s)…", expanded=True) as status:
        log_box = st.empty()
        try:
            sim_paths, log = step_run(params, st.session_state.model, out_dir, log_box)
            st.session_state.sim_paths = sim_paths
            st.session_state.analysis_log += log
            st.session_state.step2_done = True
            status.update(label="✅ Step 2/3 — Simulations complete",
                          state="complete", expanded=False)
        except Exception as exc:
            st.session_state.analysis_log += f"\nERROR (run): {exc}"
            status.update(label=f"❌ Step 2/3 failed: {exc}", state="error")

# ── STEP 3 — POST-PROCESS ────────────────────────────────────────────────────
elif post_btn:
    if st.session_state.sim_paths is None or st.session_state.params is None:
        st.error("Run steps 1 and 2 first.")
        st.stop()
    params  = st.session_state.params
    out_dir = st.session_state.out_dir
    with st.status("Step 3/3 — Post-processing…", expanded=True) as status:
        log_box = st.empty()
        try:
            log = step_post(params, st.session_state.sim_paths, out_dir, log_box)
            st.session_state.analysis_log += log
            status.update(label="✅ Step 3/3 — Post-processing complete",
                          state="complete", expanded=False)
        except Exception as exc:
            st.session_state.analysis_log += f"\nERROR (post): {exc}"
            status.update(label=f"❌ Step 3/3 failed: {exc}", state="error")

# ── RUN ALL — 1 → 2 → 3 in one click ─────────────────────────────────────────
elif all_btn:
    params = _collect_params()
    errors, warnings = validate(params)
    if errors:
        st.error("Please fix the following input errors before running:")
        for m in errors:
            st.markdown(f"- {m}")
        st.stop()
    for w in warnings:
        st.warning(w, icon="⚠️")

    cache_id = params_hash(params)
    out_dir  = os.path.join(RUNS_DIR, cache_id)
    os.makedirs(out_dir, exist_ok=True)

    if all(os.path.exists(f) for f in _expected_outputs(out_dir)):
        st.session_state.params = params
        st.session_state.out_dir = out_dir
        st.session_state.step1_done = True
        st.session_state.step2_done = True
        st.session_state.analysis_log = f"♻️ Cache hit — reused runs/{cache_id}/\n"
        st.success(f"♻️ Cache hit — reusing `runs/{cache_id}/`. "
                   f"All three steps already complete; results shown below.")
    else:
        _reset_pipeline()
        st.session_state.params = params
        st.session_state.out_dir = out_dir
        n = int(params["n_seeds"])
        with st.status("Running full pipeline (1 → 2 → 3)…", expanded=True) as status:
            log_box = st.empty()
            try:
                status.write("Step 1/3 — Building model…")
                model, log1 = step_build(params, out_dir, log_box)
                st.session_state.model = model
                st.session_state.step1_done = True

                status.write(f"Step 2/3 — Running {n} simulation(s)…")
                sim_paths, log2 = step_run(params, model, out_dir, log_box)
                st.session_state.sim_paths = sim_paths
                st.session_state.step2_done = True

                status.write("Step 3/3 — Post-processing…")
                log3 = step_post(params, sim_paths, out_dir, log_box)

                st.session_state.analysis_log = log1 + log2 + log3
                status.update(label="✅ Pipeline complete (1 → 2 → 3)",
                              state="complete", expanded=False)
            except Exception as exc:
                st.session_state.analysis_log = f"ERROR (run-all): {exc}"
                status.update(label=f"❌ Pipeline failed: {exc}", state="error")

else:
    if st.session_state.out_dir is None:
        st.info(
            "👈 Set parameters in the sidebar, then run steps **1 → 2 → 3**.",
            icon="ℹ️",
        )
        st.markdown("""
    **Workflow overview**

    | Step | Function | Description |
    |------|----------|-------------|
    | 1 | `workflow_01_build.build()` | Build OrcaFlex model |
    | 2 | `workflow_02_run.run()`     | Static + dynamic simulation(s); supports N seeds |
    | 3 | `workflow_03_results.post_process()` | Plots + text report; seed-aggregated extremes |

    All outputs go to `./runs/<hash>/`; identical parameter sets reuse the cache.
    """)


# ── Persistent Results ────────────────────────────────────────────────────────
if st.session_state.out_dir and os.path.isdir(st.session_state.out_dir):
    out_dir = st.session_state.out_dir
    fig1    = os.path.join(out_dir, "fig1_platform_motions.png")
    fig2    = os.path.join(out_dir, "fig2_mooring_tension.png")
    fig3    = os.path.join(out_dir, "fig3_cable_tension_curvature.png")
    report  = os.path.join(out_dir, "results_report.txt")

    st.divider()
    st.subheader("📊 Results")
    st.caption(f"Output directory: `{os.path.relpath(out_dir, HERE)}`")

    col1, col2 = st.columns(2)
    with col1:
        if os.path.exists(fig1):
            st.image(fig1, caption="Platform 6-DOF Motions", use_container_width=True)
        if os.path.exists(fig3):
            st.image(fig3, caption="Cable Tension & Curvature", use_container_width=True)
    with col2:
        if os.path.exists(fig2):
            st.image(fig2, caption="Mooring Tension Envelopes", use_container_width=True)
        if os.path.exists(report):
            with open(report, "r", encoding="utf-8") as f:
                report_text = f.read()
            st.download_button("📥 Download Report (.txt)", report_text,
                               file_name="results_report.txt")

    with st.expander("📄 Full Text Report"):
        if os.path.exists(report):
            with open(report, "r", encoding="utf-8") as f:
                st.text(f.read())

    with st.expander("🖥️ Console Log"):
        st.code(st.session_state.analysis_log or "(empty)", language="bash")
