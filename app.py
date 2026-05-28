"""
OrcaFlex FOWT Analysis — Streamlit GUI
=======================================
Wraps workflow_01_build.py → workflow_02_run.py → workflow_03_results.py.

Maintenance guide
-----------------
• To ADD a new input parameter:
    1. Add a widget in the relevant st.expander section below.
    2. Add the key to the `params` dict that is passed to run_workflow().
    3. In run_workflow(), write the value into the temp config file or
       pass it as an environment variable read by the workflow scripts.

• To ADD a new result plot:
    Add an st.image() or st.pyplot() call in the "Results" section.

• To change workflow scripts:
    The three subprocess calls in run_workflow() are the only integration
    points — swap script names there if you rename the workflow files.
"""

import os
import subprocess
import sys
import tempfile
import textwrap

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))

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

    # ── Site ──────────────────────────────────────────────────────────────────
    with st.expander("🏔️ Site", expanded=True):
        water_depth = st.number_input(
            "Water Depth (m)", value=200.0, min_value=50.0, max_value=3000.0, step=10.0
        )

    # ── Sea State ─────────────────────────────────────────────────────────────
    with st.expander("🌊 Sea State (ULS / 50-yr)", expanded=True):
        wave_hs        = st.number_input("Hs — Significant Wave Height (m)",  value=5.5,   min_value=0.5,   max_value=25.0,  step=0.5)
        wave_tp        = st.number_input("Tp — Spectral Peak Period (s)",     value=14.0,  min_value=3.0,   max_value=30.0,  step=0.5)
        wave_direction = st.number_input("Wave Direction (deg)",              value=0.0,   min_value=0.0,   max_value=360.0, step=15.0)

    # ── Wind ──────────────────────────────────────────────────────────────────
    with st.expander("💨 Wind"):
        wind_speed     = st.number_input("Wind Speed — 10-min mean (m/s)",   value=18.0,  min_value=0.0,   max_value=70.0,  step=1.0)
        wind_direction = st.number_input("Wind Direction (deg)",             value=180.0, min_value=0.0,   max_value=360.0, step=15.0)

    # ── Current ───────────────────────────────────────────────────────────────
    with st.expander("🌀 Current"):
        current_speed = st.number_input("Current Speed — surface (m/s)",    value=0.8,   min_value=0.0,   max_value=5.0,   step=0.1)
        current_dir   = st.number_input("Current Direction (deg)",          value=315.0, min_value=0.0,   max_value=360.0, step=15.0)

    # ── Mooring ───────────────────────────────────────────────────────────────
    with st.expander("⚓ Mooring System"):
        mooring_mbl    = st.number_input("MBL — Min. Breaking Load (kN)",   value=15800.0, min_value=1000.0, max_value=50000.0, step=100.0)
        fairlead_radius= st.number_input("Fairlead Radius (m)",             value=45.0,  min_value=10.0,  max_value=100.0, step=1.0)
        fairlead_depth = st.number_input("Fairlead Depth below WL (m, −ve)",value=-20.0, min_value=-60.0, max_value=0.0,   step=1.0)
        anchor_radius  = st.number_input("Anchor Radius (m)",               value=600.0, min_value=100.0, max_value=2000.0,step=10.0)
        mooring_length = st.number_input("Chain Length per Leg (m)",        value=660.0, min_value=100.0, max_value=3000.0,step=10.0)
        st.caption("Per-line orientation & statics")
        _m_tabs = st.tabs(["Mooring 1 (0°)", "Mooring 2 (120°)", "Mooring 3 (240°)"])
        _m_headings = [0.0, 120.0, 240.0]
        mooring_per_line = []
        for _mi, (_tab, _hdg) in enumerate(zip(_m_tabs, _m_headings), start=1):
            with _tab:
                st.caption("End A (fairlead) orientation")
                _enda_az  = st.number_input("End A Azimuth (deg)",     value=_hdg,  min_value=0.0,    max_value=360.0, step=15.0, key=f"m{_mi}_enda_az")
                _enda_dec = st.number_input("End A Declination (deg)", value=0.0,   min_value=-90.0,  max_value=90.0,  step=5.0,  key=f"m{_mi}_enda_dec",
                                            help="0 = horizontal connection at fairlead")
                _enda_gam = st.number_input("End A Gamma (deg)",       value=0.0,   min_value=-180.0, max_value=180.0, step=5.0,  key=f"m{_mi}_enda_gam")
                st.caption("End B (anchor) orientation")
                _endb_az  = st.number_input("End B Azimuth (deg)",     value=_hdg,  min_value=0.0,    max_value=360.0, step=15.0, key=f"m{_mi}_endb_az")
                _endb_dec = st.number_input("End B Declination (deg)", value=90.0,  min_value=-90.0,  max_value=90.0,  step=5.0,  key=f"m{_mi}_endb_dec",
                                            help="90 = vertical at anchor")
                _endb_gam = st.number_input("End B Gamma (deg)",       value=0.0,   min_value=-180.0, max_value=180.0, step=5.0,  key=f"m{_mi}_endb_gam")
                st.caption("Statics")
                _lay_az   = st.number_input("Lay Azimuth (deg)",       value=(_hdg + 180.0) % 360.0, min_value=0.0, max_value=360.0, step=15.0, key=f"m{_mi}_lay_az")
                _as_laid  = st.number_input("As-Laid Tension (kN)",    value=0.0,   min_value=0.0,    max_value=5000.0,step=10.0, key=f"m{_mi}_as_laid",
                                            help="0 = OrcaFlex calculates from geometry")
                mooring_per_line.append(dict(
                    enda_azimuth=_enda_az, enda_declination=_enda_dec, enda_gamma=_enda_gam,
                    endb_azimuth=_endb_az, endb_declination=_endb_dec, endb_gamma=_endb_gam,
                    lay_azimuth=_lay_az, as_laid_tension=_as_laid,
                ))

    # ── Dynamic Cable ─────────────────────────────────────────────────────────
    with st.expander("🔌 Dynamic Export Cable"):
        cable_mbr      = st.number_input("MBR — Min. Allowable Bend Radius (m)", value=2.5, min_value=0.5, max_value=10.0, step=0.1)
        cable_hangoff_x= st.number_input("Hang-off X (m)",                  value=-35.0, min_value=-200.0, max_value=0.0,  step=5.0)
        cable_hangoff_z= st.number_input("Hang-off Depth below WL (m, −ve)",value=-15.0, min_value=-60.0,  max_value=0.0,  step=1.0)
        cable_seabed_x = st.number_input("J-tube X on Seabed (m)",          value=-420.0,min_value=-2000.0,max_value=0.0,  step=10.0)
        st.caption("End A (hang-off / I-tube) orientation")
        cable_enda_azimuth     = st.number_input("End A Azimuth (deg)",     value=180.0, min_value=0.0,   max_value=360.0, step=15.0, key="cab_enda_az")
        cable_enda_declination = st.number_input("End A Declination (deg)", value=0.0,   min_value=-90.0, max_value=90.0,  step=5.0,  key="cab_enda_dec",
                                                 help="0 = horizontal I-tube exit")
        cable_enda_gamma       = st.number_input("End A Gamma (deg)",       value=0.0,   min_value=-180.0,max_value=180.0, step=5.0,  key="cab_enda_gam")
        st.caption("End B (J-tube / seabed) orientation")
        cable_endb_azimuth     = st.number_input("End B Azimuth (deg)",     value=0.0,   min_value=0.0,   max_value=360.0, step=15.0, key="cab_endb_az")
        cable_endb_declination = st.number_input("End B Declination (deg)", value=90.0,  min_value=-90.0, max_value=90.0,  step=5.0,  key="cab_endb_dec",
                                                 help="90 = vertical entry into J-tube")
        cable_endb_gamma       = st.number_input("End B Gamma (deg)",       value=0.0,   min_value=-180.0,max_value=180.0, step=5.0,  key="cab_endb_gam")
        st.caption("Statics")
        cable_lay_azimuth     = st.number_input("Lay Azimuth (deg)",        value=360.0, min_value=0.0,   max_value=360.0, step=15.0, key="cab_lay_az",
                                                help="Initial lay direction toward seabed J-tube")
        cable_as_laid_tension = st.number_input("As-Laid Tension (kN)",     value=0.0,   min_value=0.0,   max_value=5000.0,step=10.0, key="cab_as_laid",
                                                help="0 = OrcaFlex calculates from geometry")

    # ── Analysis ──────────────────────────────────────────────────────────────
    with st.expander("⏱️ Analysis Durations"):
        buildup_duration  = st.number_input("Build-up Duration (s)",        value=30.0,   min_value=10.0,  max_value=300.0, step=10.0)
        analysis_duration = st.number_input("Analysis Duration (s)",        value=3600.0, min_value=600.0, max_value=10800.0,step=600.0,
                                            help="1 h = 3600 s for ULS; use ≥ 10800 s (3 h) for fatigue")

    st.divider()
    run_btn = st.button("▶  Run Analysis", type="primary", use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# HELPER — write a temporary project_config override and run the workflows
# ═════════════════════════════════════════════════════════════════════════════

def run_workflow(params: dict) -> tuple[bool, str]:
    """
    Writes all GUI parameters into a temp config file, then runs the three
    workflow scripts sequentially. Returns (success, log_text).

    Integration point: if you add new parameters, extend the config template
    below and pass the extra values in `params`.
    """
    config_content = textwrap.dedent(f"""
        # Auto-generated by app.py — do not edit manually
        WATER_DEPTH       = {params['water_depth']}
        MOORING_MBL       = {params['mooring_mbl']}
        CABLE_MBR         = {params['cable_mbr']}
        BUILDUP_DURATION  = {params['buildup_duration']}
        ANALYSIS_DURATION = {params['analysis_duration']}
    """).strip()

    config_path = os.path.join(HERE, "project_config.py")

    # --- write workflow_01 parameter overrides via environment variables ------
    env = os.environ.copy()
    env.update({
        "GUI_WAVE_HS":          str(params["wave_hs"]),
        "GUI_WAVE_TP":          str(params["wave_tp"]),
        "GUI_WAVE_DIRECTION":   str(params["wave_direction"]),
        "GUI_WIND_SPEED":       str(params["wind_speed"]),
        "GUI_WIND_DIRECTION":   str(params["wind_direction"]),
        "GUI_CURRENT_SPEED":    str(params["current_speed"]),
        "GUI_CURRENT_DIR":      str(params["current_dir"]),
        "GUI_FAIRLEAD_RADIUS":  str(params["fairlead_radius"]),
        "GUI_FAIRLEAD_DEPTH":   str(params["fairlead_depth"]),
        "GUI_ANCHOR_RADIUS":    str(params["anchor_radius"]),
        "GUI_MOORING_LENGTH":   str(params["mooring_length"]),
        "GUI_CABLE_HANGOFF_X":          str(params["cable_hangoff_x"]),
        "GUI_CABLE_HANGOFF_Z":          str(params["cable_hangoff_z"]),
        "GUI_CABLE_SEABED_X":           str(params["cable_seabed_x"]),
        **{f"GUI_MOORING{i+1}_{k.upper()}": str(params["mooring_per_line"][i][k])
           for i in range(3)
           for k in ["enda_azimuth","enda_declination","enda_gamma",
                     "endb_azimuth","endb_declination","endb_gamma",
                     "lay_azimuth","as_laid_tension"]},
        "GUI_CABLE_ENDA_AZIMUTH":       str(params["cable_enda_azimuth"]),
        "GUI_CABLE_ENDA_DECLINATION":   str(params["cable_enda_declination"]),
        "GUI_CABLE_ENDA_GAMMA":         str(params["cable_enda_gamma"]),
        "GUI_CABLE_ENDB_AZIMUTH":       str(params["cable_endb_azimuth"]),
        "GUI_CABLE_ENDB_DECLINATION":   str(params["cable_endb_declination"]),
        "GUI_CABLE_ENDB_GAMMA":         str(params["cable_endb_gamma"]),
        "GUI_CABLE_LAY_AZIMUTH":        str(params["cable_lay_azimuth"]),
        "GUI_CABLE_AS_LAID_TENSION":    str(params["cable_as_laid_tension"]),
    })

    # Temporarily overwrite project_config.py with GUI values
    original_config = open(config_path).read()
    open(config_path, "w").write(config_content)

    log_lines = []
    success = True
    try:
        for step, script in enumerate(
            ["workflow_01_build.py", "workflow_02_run.py", "workflow_03_results.py"], 1
        ):
            log_lines.append(f"\n{'─'*50}\nStep {step}: {script}\n{'─'*50}")
            result = subprocess.run(
                [sys.executable, os.path.join(HERE, script)],
                capture_output=True, text=True, env=env, cwd=HERE
            )
            log_lines.append(result.stdout)
            if result.returncode != 0:
                log_lines.append(f"ERROR:\n{result.stderr}")
                success = False
                break
    finally:
        # Always restore original project_config.py
        open(config_path, "w").write(original_config)

    return success, "\n".join(log_lines)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN AREA — run + results
# ═════════════════════════════════════════════════════════════════════════════

if run_btn:
    params = dict(
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
    )

    progress = st.progress(0, text="Starting…")

    with st.status("Running OrcaFlex analysis…", expanded=True) as status:
        st.write("Step 1/3 — Building model…")
        progress.progress(10, text="Step 1/3 — Building model…")

        success, log = run_workflow(params)

        progress.progress(100, text="Done!" if success else "Failed")
        if success:
            status.update(label="✅ Analysis complete!", state="complete")
        else:
            status.update(label="❌ Analysis failed — see log below", state="error")

    # ── Results ───────────────────────────────────────────────────────────────
    if success:
        st.subheader("📊 Results")
        col1, col2 = st.columns(2)

        fig1 = os.path.join(HERE, "fig1_platform_motions.png")
        fig2 = os.path.join(HERE, "fig2_mooring_tension.png")
        fig3 = os.path.join(HERE, "fig3_cable_tension_curvature.png")
        report = os.path.join(HERE, "results_report.txt")

        with col1:
            if os.path.exists(fig1):
                st.image(fig1, caption="Platform 6-DOF Motions", use_container_width=True)
            if os.path.exists(fig3):
                st.image(fig3, caption="Cable Tension & Curvature", use_container_width=True)
        with col2:
            if os.path.exists(fig2):
                st.image(fig2, caption="Mooring Tension Envelopes", use_container_width=True)
            if os.path.exists(report):
                with open(report) as f:
                    st.download_button("📥 Download Report (.txt)", f.read(),
                                       file_name="results_report.txt")

        # Full text report
        with st.expander("📄 Full Text Report"):
            if os.path.exists(report):
                st.text(open(report).read())

    # ── Console log ───────────────────────────────────────────────────────────
    with st.expander("🖥️ Console Log", expanded=not success):
        st.code(log, language="bash")

else:
    # ── Welcome screen ────────────────────────────────────────────────────────
    st.info(
        "👈 Set your parameters in the sidebar, then click **▶ Run Analysis**.",
        icon="ℹ️",
    )
    st.markdown("""
    **Workflow overview**

    | Step | Script | Description |
    |------|--------|-------------|
    | 1 | `workflow_01_build.py` | Build OrcaFlex model (platform, mooring, cable, environment) |
    | 2 | `workflow_02_run.py` | Run statics + time-domain dynamics, save `.sim` |
    | 3 | `workflow_03_results.py` | Post-process: motions, tensions, extreme stats, plots |
    """)
