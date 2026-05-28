"""
OrcaFlex Workflow — Step 1: Model Build (Pre-Processing)
========================================================
Use-case : Floating Offshore Wind Turbine (FOWT) — semi-submersible platform
           with a 3-leg spread catenary mooring system and a dynamic export cable.

The same workflow structure adapts to Marine Operations (heavy-lift, towing,
pipe-lay); see MARINE OPS NOTES inline below.

Model layout
  Platform    : semi-sub hull as a Vessel at the global origin
  Mooring 1–3 : R4-grade stud-link chain, 120° spread, catenary to seabed anchors
  ExportCable : 3-section lazy-wave dynamic power cable to seabed J-tube
  Environment : JONSWAP sea state + steady wind + uniform current

Run order: workflow_01_build.py  →  workflow_02_run.py  →  workflow_03_results.py
"""

import math
import os
import OrcFxAPI

import project_config as cfg
from project_config import GUI_DEFAULTS as D

HERE = os.path.dirname(os.path.abspath(__file__))   # write outputs next to this script

def _env(key, default):
    """Read a float override from an environment variable set by the GUI.

    Raises a clear error if the env var is set but cannot be parsed as float,
    so user input mistakes don't fail later with cryptic OrcFxAPI errors.
    """
    val = os.environ.get(key)
    if val is None:
        return float(default)
    try:
        return float(val)
    except ValueError as exc:
        raise ValueError(f"Environment variable {key}={val!r} is not a valid number") from exc

# ══════════════════════════════════════════════════════════════════════════════
# PROJECT PARAMETERS
#   • Defaults come from project_config.GUI_DEFAULTS (single source of truth).
#   • Each value can be overridden at runtime via a GUI_<KEY> env var.
# ══════════════════════════════════════════════════════════════════════════════

# Site / global
WATER_DEPTH       = _env("GUI_WATER_DEPTH",       cfg.WATER_DEPTH)
MOORING_MBL       = _env("GUI_MOORING_MBL",       cfg.MOORING_MBL)
BUILDUP_DURATION  = _env("GUI_BUILDUP_DURATION",  cfg.BUILDUP_DURATION)
ANALYSIS_DURATION = _env("GUI_ANALYSIS_DURATION", cfg.ANALYSIS_DURATION)

# Design sea state (ULS / 50-yr extreme)
WAVE_HS         = _env("GUI_WAVE_HS",         D["wave_hs"])
WAVE_TP         = _env("GUI_WAVE_TP",         D["wave_tp"])
WAVE_DIRECTION  = _env("GUI_WAVE_DIRECTION",  D["wave_direction"])
WIND_SPEED      = _env("GUI_WIND_SPEED",      D["wind_speed"])
WIND_DIRECTION  = _env("GUI_WIND_DIRECTION",  D["wind_direction"])
CURRENT_SPEED   = _env("GUI_CURRENT_SPEED",   D["current_speed"])
CURRENT_DIR     = _env("GUI_CURRENT_DIR",     D["current_dir"])

# Mooring geometry (3-leg spread catenary, symmetric about platform)
FAIRLEAD_RADIUS = _env("GUI_FAIRLEAD_RADIUS", D["fairlead_radius"])
FAIRLEAD_DEPTH  = _env("GUI_FAIRLEAD_DEPTH",  D["fairlead_depth"])
ANCHOR_RADIUS   = _env("GUI_ANCHOR_RADIUS",   D["anchor_radius"])
MOORING_LENGTH  = _env("GUI_MOORING_LENGTH",  D["mooring_length"])

# Per-line orientation defaults (overridden per leg via GUI_MOORING{i}_* env vars)
MOORING_ENDA_DECLINATION = D["mooring_enda_declination"]
MOORING_ENDA_GAMMA       = D["mooring_enda_gamma"]
MOORING_ENDB_DECLINATION = D["mooring_endb_declination"]
MOORING_ENDB_GAMMA       = D["mooring_endb_gamma"]
MOORING_LAY_AZIMUTH      = D["mooring_lay_azimuth_off"]
MOORING_AS_LAID_TENSION  = D["mooring_as_laid_tension"]

# Dynamic cable geometry (global coordinates)
CABLE_HANGOFF_X = _env("GUI_CABLE_HANGOFF_X", D["cable_hangoff_x"])
CABLE_HANGOFF_Z = _env("GUI_CABLE_HANGOFF_Z", D["cable_hangoff_z"])
CABLE_SEABED_X  = _env("GUI_CABLE_SEABED_X",  D["cable_seabed_x"])

# Cable end orientations
CABLE_ENDA_AZIMUTH     = _env("GUI_CABLE_ENDA_AZIMUTH",     D["cable_enda_azimuth"])
CABLE_ENDA_DECLINATION = _env("GUI_CABLE_ENDA_DECLINATION", D["cable_enda_declination"])
CABLE_ENDA_GAMMA       = _env("GUI_CABLE_ENDA_GAMMA",       D["cable_enda_gamma"])
CABLE_ENDB_AZIMUTH     = _env("GUI_CABLE_ENDB_AZIMUTH",     D["cable_endb_azimuth"])
CABLE_ENDB_DECLINATION = _env("GUI_CABLE_ENDB_DECLINATION", D["cable_endb_declination"])
CABLE_ENDB_GAMMA       = _env("GUI_CABLE_ENDB_GAMMA",       D["cable_endb_gamma"])

# Cable statics
CABLE_LAY_AZIMUTH     = _env("GUI_CABLE_LAY_AZIMUTH",     D["cable_lay_azimuth"])
CABLE_AS_LAID_TENSION = _env("GUI_CABLE_AS_LAID_TENSION", D["cable_as_laid_tension"])

# ══════════════════════════════════════════════════════════════════════════════
# 1. MODEL AND GENERAL SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
model = OrcFxAPI.Model()

general = model.general
# Stage 0 = ramped build-up from rest;  Stage 1 = statistical analysis period
general.StageDuration = BUILDUP_DURATION, ANALYSIS_DURATION

# ══════════════════════════════════════════════════════════════════════════════
# 2. ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════
env = model.environment
env.WaterDepth = WATER_DEPTH

# Irregular sea state — JONSWAP spectrum
# Alternatives: "Dean Stream" for current-dominated, "Frequency domain" for FD analysis
env.WaveType      = "JONSWAP"
env.WaveHs        = WAVE_HS
env.WaveTp        = WAVE_TP
env.WaveDirection = WAVE_DIRECTION
env.UserSpecifiedRandomWaveSeeds = "Yes"
env.WaveSeed = 314159     # fix seed for repeatability; vary for multi-seed fatigue

# Steady wind (spatial and temporal uniform)
# For wind turbine: model rotor thrust as a time-varying applied load on the
# platform, or use an external function to compute aerodynamic loads each step.
# For NPD wind spectrum (low-frequency excitation): set WaveType = "NPD spectrum".
env.WindType      = "Constant"
env.WindSpeed     = WIND_SPEED
env.WindDirection = WIND_DIRECTION

# Uniform current profile (single scalar value for each property)
# For a depth-varying profile, add rows via SetDataRowCount first:
#   env.SetDataRowCount("RefCurrentSpeed", 3)
#   env.RefCurrentDepth     = 0.0, -50.0, -WATER_DEPTH
#   env.RefCurrentSpeed     = 0.8,  0.5,   0.2
#   env.RefCurrentDirection = 315.0, 315.0, 315.0
env.RefCurrentSpeed     = CURRENT_SPEED
env.RefCurrentDirection = CURRENT_DIR

# ══════════════════════════════════════════════════════════════════════════════
# 3. PLATFORM (hull)
# ══════════════════════════════════════════════════════════════════════════════
# Modelled as a Vessel (uses vessel type RAOs for hydrodynamic response).
# For a detailed diffraction-based hull, import a vessel type built from
# WAMIT / AQWA output using OrcaFlex's vessel type editor or .vtp import.
#
# MARINE OPS — crane vessel:
#   crane_vessel = model.CreateObject(OrcFxAPI.ObjectType.Vessel, "CraneVessel")
#   crane_vessel.InitialHeading = 270.0   # vessel heading (bow into weather)
#   # Define crane tip as an attachment point, then connect lift wire to it.
#
# NOTE: this Vessel uses the default VesselType (no RAOs, no wind / current
# drag coefficients, no diffraction database). Consequently the platform's
# only response to first-order waves is through the mooring + cable reactions
# in the wave-loaded plane, and Sway / Roll / Yaw will be zero. For a
# representative FOWT model you must:
#   1. Create a VesselType, import RAOs / QTF / added mass from WAMIT or AQWA
#      (model.CreateObject(OrcFxAPI.ObjectType.VesselType, "Semi-Sub")), and
#   2. Assign it here:   platform.VesselType = "Semi-Sub"; platform.Draught = "Draught1"
platform = model.CreateObject(OrcFxAPI.ObjectType.Vessel, "Platform")

# ── OC4-DeepCwind 3-column semi-sub visual representation ────────────────────
# Shape objects are attached to the Platform and move with it in the 3D view.
# Dimensions from: Robertson et al. (2014) OC4-DeepCwind definition report.
#
# Platform local coordinate system (origin = waterline amidships):
#   +X forward, +Y port, +Z up
#   z =   0  → waterline
#   z = -20  → keel
#   z = +12  → top of column
# Shape InitialZ is the CENTRE of each cylinder in the Platform local frame.

OC4_COL_OFFSET_R = 40.868   # m  radius: platform centre → offset column centre
OC4_DRAFT        = 20.0     # m  platform draft
OC4_FREEBOARD    = 12.0     # m  column height above waterline
OC4_CENTRAL_D    =  6.5     # m  central column outer diameter
OC4_OFFSET_COL_D = 12.0     # m  upper offset column outer diameter
OC4_BASE_D       = 24.0     # m  base column outer diameter
OC4_BASE_H       =  6.0     # m  base column height
OC4_UPPER_COL_H  = OC4_DRAFT + OC4_FREEBOARD - OC4_BASE_H   # 26 m

def _add_cylinder(name, cx, cy, z_bottom, height, diameter):
    """Create a cylindrical Shape attached to the Platform vessel."""
    s = model.CreateObject(OrcFxAPI.ObjectType.Shape, name)
    s.SetData("Connection",    0, platform.Name)
    s.SetData("Shape",         0, "Cylinder")
    s.SetData("OriginX",       0, cx)
    s.SetData("OriginY",       0, cy)
    s.SetData("OriginZ",       0, z_bottom + height / 2.0)   # cylinder centre
    s.SetData("Length",        0, height)
    s.SetData("OuterDiameter", 0, diameter)
    s.SetData("InnerDiameter", 0, 0.0)
    return s

# Central column: keel → top (full height = draft + freeboard = 32 m)
_add_cylinder("Shape_CentralColumn", 0.0, 0.0,
              z_bottom=-OC4_DRAFT,
              height=OC4_DRAFT + OC4_FREEBOARD,
              diameter=OC4_CENTRAL_D)

# 3 × upper offset columns + base columns at 0° / 120° / 240°
for _i, _hdg in enumerate([0.0, 120.0, 240.0]):
    _rad = math.radians(_hdg)
    _cx  = OC4_COL_OFFSET_R * math.cos(_rad)
    _cy  = OC4_COL_OFFSET_R * math.sin(_rad)

    # Upper offset column (above base section)
    _add_cylinder(f"Shape_OffsetColumn{_i+1}", _cx, _cy,
                  z_bottom=-OC4_DRAFT + OC4_BASE_H,
                  height=OC4_UPPER_COL_H,
                  diameter=OC4_OFFSET_COL_D)

    # Base column (large-diameter lower section)
    _add_cylinder(f"Shape_BaseColumn{_i+1}", _cx, _cy,
                  z_bottom=-OC4_DRAFT,
                  height=OC4_BASE_H,
                  diameter=OC4_BASE_D)

print("OC4 semi-sub geometry: 1 central + 3 offset + 3 base columns added.")

# ══════════════════════════════════════════════════════════════════════════════
# 4. LINE TYPES
# ══════════════════════════════════════════════════════════════════════════════
# Note: LineType properties are non-indexed scalars (not per-section tables).
# All values are in model default units: kN, m, te (metric tonne).
# Verify against manufacturer data sheets / project line type library.

# R4 stud-link chain — 114 mm bar diameter
chain = model.CreateObject(OrcFxAPI.ObjectType.LineType, "R4 Chain 114mm")
chain.OD                = 0.311   # m   effective OD (≈ 2.73 × bar dia)
chain.ID                = 0.0    # m   solid cross-section (default ID=0.25 must be overridden)
chain.MassPerUnitLength = 0.303   # te/m  in-air linear mass
chain.EA                = 854000  # kN   axial stiffness
chain.EIx               = 0.0    # kN·m²  negligible bending stiffness
chain.EIy               = 0.0
chain.GJ                = 0.0    # kN·m²  negligible torsion

# Dynamic HVAC export cable — 220 kV three-core (representative)
# Replace with project-specific cable design report values.
# Mass must be > buoyancy = π/4 × OD² × 1.025 = 0.039 te/m; use 0.060 te/m.
cable_type = model.CreateObject(OrcFxAPI.ObjectType.LineType, "HVAC Cable 220kV")
cable_type.OD                = 0.220   # m
cable_type.ID                = 0.0     # m   solid cross-section (default ID=0.25 must be overridden)
cable_type.MassPerUnitLength = 0.060   # te/m  negatively buoyant (buoyancy≈0.039 te/m)
cable_type.EA                = 15000   # kN
cable_type.EIx               = 8.0    # kN·m²  must set both EIx and EIy (default EIx=120, EIy=∞)
cable_type.EIy               = 8.0    # kN·m²  isotropic → no torsion requirement

# Buoyancy-module section — cable + clamped cylindrical buoyancy modules
# Net submerged weight = mass − buoyancy = 0.070 − π/4×0.50²×1.025 ≈ −0.131 te/m (floats)
# This positive buoyancy creates the hog bend in the lazy-wave configuration.
buoy_type = model.CreateObject(OrcFxAPI.ObjectType.LineType, "HVAC Cable + BuoyancyModules")
buoy_type.OD                = 0.500   # m   outer diameter of buoyancy module clamp
buoy_type.ID                = 0.0
buoy_type.MassPerUnitLength = 0.070   # te/m  cable + clamp rings
buoy_type.EA                = 15000   # kN   axial stiffness from cable core
buoy_type.EIx               = 8.0    # kN·m²  must match EIy (isotropic)
buoy_type.EIy               = 8.0

# MARINE OPS — add wire rope and sling line types:
#   wire = model.CreateObject(OrcFxAPI.ObjectType.LineType, "Crane Wire 76mm")
#   wire.OD = 0.083; wire.MassPerUnitLength = 0.022; wire.EA = 200000

# ══════════════════════════════════════════════════════════════════════════════
# 5. MOORING LINES — 3-leg spread catenary at 30° / 150° / 270° azimuth
# ══════════════════════════════════════════════════════════════════════════════
# Headings are offset from the primary wave direction so no leg is directly
# upwave or downwave.  Adjust to the project-specific anchor pattern.
MOORING_HEADINGS = [0.0, 120.0, 240.0]   # degrees (global azimuth from +X)

for i, hdg_deg in enumerate(MOORING_HEADINGS, start=1):
    rad = math.radians(hdg_deg)
    ml  = model.CreateObject(OrcFxAPI.ObjectType.Line, f"Mooring{i}")

    # End A — fairlead, rigidly connected to platform hull
    ml.EndAConnection = platform.Name
    ml.EndAX          = FAIRLEAD_RADIUS * math.cos(rad)
    ml.EndAY          = FAIRLEAD_RADIUS * math.sin(rad)
    ml.EndAZ          = FAIRLEAD_DEPTH

    # End B — seabed anchor (fixed point; EndBConnection defaults to "Anchored")
    ml.EndBX = ANCHOR_RADIUS * math.cos(rad)
    ml.EndBY = ANCHOR_RADIUS * math.sin(rad)
    ml.EndBZ = -WATER_DEPTH

    # Single-section full-chain catenary leg.
    # For a chain-wire-chain composite: provide 3-element tuples, e.g.:
    #   ml.LineType = "R4 Chain 114mm", "Wire Rope 95mm", "R4 Chain 114mm"
    #   ml.Length   = 150.0, 510.0, 200.0    # m  (bottom, mid, top sections)
    ml.LineType            = chain.Name,      # trailing comma → 1-element tuple
    ml.Length              = MOORING_LENGTH,
    ml.TargetSegmentLength = 10.0,            # m (coarser in mid-water catenary)

    # Per-line orientation — GUI sends GUI_MOORING{i}_ENDA_AZIMUTH etc.
    # Defaults fall back to the leg heading / shared constants when run standalone.
    ml.EndAAzimuth     = _env(f"GUI_MOORING{i}_ENDA_AZIMUTH",     hdg_deg)
    ml.EndADeclination = _env(f"GUI_MOORING{i}_ENDA_DECLINATION", MOORING_ENDA_DECLINATION)
    ml.EndAGamma       = _env(f"GUI_MOORING{i}_ENDA_GAMMA",       MOORING_ENDA_GAMMA)

    ml.EndBAzimuth     = _env(f"GUI_MOORING{i}_ENDB_AZIMUTH",     hdg_deg)
    ml.EndBDeclination = _env(f"GUI_MOORING{i}_ENDB_DECLINATION", MOORING_ENDB_DECLINATION)
    ml.EndBGamma       = _env(f"GUI_MOORING{i}_ENDB_GAMMA",       MOORING_ENDB_GAMMA)

    # Per-line statics
    ml.LayAzimuth    = _env(f"GUI_MOORING{i}_LAY_AZIMUTH",    (hdg_deg + 180.0 + MOORING_LAY_AZIMUTH) % 360.0)
    ml.AsLaidTension = _env(f"GUI_MOORING{i}_AS_LAID_TENSION", MOORING_AS_LAID_TENSION)

# ══════════════════════════════════════════════════════════════════════════════
# 6. DYNAMIC EXPORT CABLE — 3-section lazy-wave configuration
# ══════════════════════════════════════════════════════════════════════════════
# Layout: top catenary (hang-off → sag bend) → buoyancy section (hog bend)
#         → bottom catenary (touchdown zone).
# Buoyancy in the mid-section is achieved via distributed buoyancy modules;
# model those as added mass/buoyancy modifications to the line type if needed.
#
# MARINE OPS — lift wire from crane tip to hook block:
#   lift_wire = model.CreateObject(OrcFxAPI.ObjectType.Line, "LiftWire")
#   lift_wire.EndAConnection = "CraneVessel"
#   lift_wire.EndAX, lift_wire.EndAY, lift_wire.EndAZ = crane_tip_x, 0.0, crane_tip_z
#   lift_wire.EndBConnection = "HookedLoad"   # a 6D Buoy representing the lifted object
#   lift_wire.LineType = "Crane Wire 76mm",
#   lift_wire.Length   = wire_length,
cable = model.CreateObject(OrcFxAPI.ObjectType.Line, "ExportCable")

cable.EndAConnection = platform.Name
cable.EndAX          = CABLE_HANGOFF_X
cable.EndAY          = 0.0
cable.EndAZ          = CABLE_HANGOFF_Z

cable.EndBX = CABLE_SEABED_X   # seabed J-tube (anchored, default)
cable.EndBY = 0.0
cable.EndBZ = -WATER_DEPTH

# 3-section lazy-wave — tuple length sets number of sections automatically
# Section 1: top catenary  (hang-off → sag bend)
# Section 2: buoyancy section  (hog bend — positively buoyant with modules)
# Section 3: bottom catenary  (touchdown zone → seabed anchor)
cable.LineType            = cable_type.Name, buoy_type.Name, cable_type.Name
cable.Length              = 150.0, 120.0, 210.0   # m  (top, buoyancy, bottom)
cable.TargetSegmentLength = 5.0, 3.0, 5.0

# End A orientation (hang-off at I-tube)
cable.EndAAzimuth     = CABLE_ENDA_AZIMUTH
cable.EndADeclination = CABLE_ENDA_DECLINATION
cable.EndAGamma       = CABLE_ENDA_GAMMA

# End B orientation (J-tube entry on seabed)
cable.EndBAzimuth     = CABLE_ENDB_AZIMUTH
cable.EndBDeclination = CABLE_ENDB_DECLINATION
cable.EndBGamma       = CABLE_ENDB_GAMMA

# Statics
cable.LayAzimuth    = CABLE_LAY_AZIMUTH
cable.AsLaidTension = CABLE_AS_LAID_TENSION

# ══════════════════════════════════════════════════════════════════════════════
# 7. SAVE
# ══════════════════════════════════════════════════════════════════════════════
print("Objects in model:")
for obj in model.objects:
    print(f"  {obj}")

dat_path = os.path.join(HERE, "testModel.dat")
yml_path = os.path.join(HERE, "testModel.yml")
model.SaveData(dat_path)    # OrcaFlex binary model data
model.SaveData(yml_path)    # YAML text copy (human-readable / VCS-friendly)

print(f"\nModel saved: {dat_path}")
print(f"             {yml_path}")
print("Next step: run workflow_02_run.py")
