"""
Shared project configuration.

Single source of truth for default values. Imported by:
  • workflow_01_build.py  — model build
  • workflow_02_run.py    — simulation run
  • workflow_03_results.py — post-processing
  • app.py                — Streamlit GUI default widget values

The GUI may override any of these at runtime via environment variables
(GUI_<UPPERCASE_KEY>); the workflow scripts read them through the `_env()`
helper. If the env var is not set, the value below is used — so the same
workflow scripts work both standalone and behind the GUI.
"""

# ── Site ──────────────────────────────────────────────────────────────────────
WATER_DEPTH = 200.0          # m

# ── Mooring system ────────────────────────────────────────────────────────────
MOORING_MBL = 15800.0        # kN  R4 chain 114 mm minimum breaking load

# ── Dynamic cable ─────────────────────────────────────────────────────────────
CABLE_MBR   = 2.50           # m   minimum allowable bend radius

# ── Analysis ──────────────────────────────────────────────────────────────────
BUILDUP_DURATION  =   30.0   # s   ramp from rest (≥ 2 × Tp recommended)
ANALYSIS_DURATION = 3600.0   # s   1-h analysis window (≥ 3 h for fatigue)

# ══════════════════════════════════════════════════════════════════════════════
# GUI_DEFAULTS — every parameter the Streamlit GUI exposes
# ══════════════════════════════════════════════════════════════════════════════
# One dict, one source of truth. Both app.py (widget `value=`) and
# workflow_01_build.py (`_env(..., GUI_DEFAULTS[k])`) read from here.
GUI_DEFAULTS = {
    # Site
    "water_depth":              WATER_DEPTH,

    # Sea state (ULS / 50-yr)
    "wave_hs":                  5.5,
    "wave_tp":                 14.0,
    "wave_direction":           0.0,

    # Wind
    "wind_speed":              18.0,
    "wind_direction":         180.0,

    # Current
    "current_speed":            0.8,
    "current_dir":            315.0,

    # Mooring — shared geometry
    "mooring_mbl":              MOORING_MBL,
    "fairlead_radius":         45.0,
    "fairlead_depth":         -20.0,
    "anchor_radius":          600.0,
    "mooring_length":         660.0,

    # Mooring — per-line defaults (applied to each leg unless GUI overrides)
    "mooring_enda_declination": 0.0,    # horizontal at fairlead
    "mooring_enda_gamma":       0.0,
    "mooring_endb_declination": 90.0,   # vertical at anchor
    "mooring_endb_gamma":       0.0,
    "mooring_lay_azimuth_off":  0.0,    # added to (heading + 180) when seeding GUI
    "mooring_as_laid_tension":  0.0,

    # Dynamic cable
    "cable_mbr":                CABLE_MBR,
    "cable_hangoff_x":        -35.0,
    "cable_hangoff_z":        -15.0,
    "cable_seabed_x":        -420.0,
    "cable_enda_azimuth":     180.0,
    "cable_enda_declination":   0.0,
    "cable_enda_gamma":         0.0,
    "cable_endb_azimuth":       0.0,
    "cable_endb_declination":  90.0,
    "cable_endb_gamma":         0.0,
    "cable_lay_azimuth":      360.0,
    "cable_as_laid_tension":    0.0,

    # Analysis durations
    "buildup_duration":         BUILDUP_DURATION,
    "analysis_duration":        ANALYSIS_DURATION,

    # Post-processing
    "storm_hours":              3,      # h   storm duration for extreme stats
    "risk_pct":                 5,      # %   risk factor for extreme value query
    "period":                   1,      # analysis stage (0 = build-up, 1 = analysis)
}
