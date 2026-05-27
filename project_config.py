"""
Shared project configuration.

Constants imported by workflow_01_build.py (model build) and
workflow_03_results.py (post-processing) so they cannot drift apart.
"""

# ── Site ──────────────────────────────────────────────────────────────────────
WATER_DEPTH = 200.0          # m  (also read back from model in step 3 — this
                             #     literal is the design intent for step 1)

# ── Mooring system ────────────────────────────────────────────────────────────
MOORING_MBL = 15800.0        # kN  R4 chain 114 mm minimum breaking load

# ── Dynamic cable ─────────────────────────────────────────────────────────────
CABLE_MBR   = 2.50           # m   minimum allowable bend radius

# ── Analysis ──────────────────────────────────────────────────────────────────
BUILDUP_DURATION  =   30.0   # s   ramp from rest (≥ 2 × Tp recommended)
ANALYSIS_DURATION = 3600.0   # s   1-h analysis window (≥ 3 h for fatigue)
