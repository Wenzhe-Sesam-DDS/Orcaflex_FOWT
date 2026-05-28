"""
Shared project configuration.

Single source of truth for default values. Imported by:
  • workflow_01_build.py  — model build
  • workflow_02_run.py    — simulation run
  • workflow_03_results.py — post-processing
  • app.py                — Streamlit GUI default widget values

The Streamlit GUI overrides any default at runtime by passing a `params` dict
directly into the workflow functions (no environment variables, no on-disk
mutation of this file). The workflow scripts run standalone using these
defaults when invoked from the command line.
"""

# ── Site ──────────────────────────────────────────────────────────────────────
WATER_DEPTH = 200.0          # m

# ── Mooring system ────────────────────────────────────────────────────────────
MOORING_MBL = 15800.0        # kN  R4 chain 114 mm minimum breaking load

# 3-leg spread catenary — single source of truth for the leg azimuths.
# Used by both the model builder and the GUI to label per-line tabs.
MOORING_HEADINGS = [0.0, 120.0, 240.0]   # deg, global azimuth from +X axis

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

    # Random seeds (multi-seed runs aggregate extreme stats across all seeds)
    "wave_seed":                314159, # base WaveSeed; subsequent seeds = base + i
    "n_seeds":                  1,      # number of seeds to run (>= 1)
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def params_with_defaults(overrides: dict | None = None) -> dict:
    """Return a copy of GUI_DEFAULTS merged with `overrides` (overrides win).

    Per-line mooring overrides come through key `mooring_per_line` (a list of
    3 dicts). If absent, the builder substitutes the shared defaults.
    """
    out = dict(GUI_DEFAULTS)
    if overrides:
        out.update(overrides)
    out.setdefault("mooring_per_line", _default_mooring_per_line())
    return out


def _default_mooring_per_line() -> list[dict]:
    """3 mooring legs initialised from MOORING_HEADINGS + shared defaults."""
    d = GUI_DEFAULTS
    return [
        dict(
            enda_azimuth     = hdg,
            enda_declination = d["mooring_enda_declination"],
            enda_gamma       = d["mooring_enda_gamma"],
            endb_azimuth     = hdg,
            endb_declination = d["mooring_endb_declination"],
            endb_gamma       = d["mooring_endb_gamma"],
            lay_azimuth      = (hdg + 180.0 + d["mooring_lay_azimuth_off"]) % 360.0,
            as_laid_tension  = d["mooring_as_laid_tension"],
        )
        for hdg in MOORING_HEADINGS
    ]


def params_hash(params: dict) -> str:
    """Stable short hash of a params dict, for output-directory caching."""
    import hashlib
    import json
    blob = json.dumps(params, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]
