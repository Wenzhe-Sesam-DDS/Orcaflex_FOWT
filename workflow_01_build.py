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

from project_config import (
    WATER_DEPTH,
    MOORING_MBL,
    BUILDUP_DURATION,
    ANALYSIS_DURATION,
)

HERE = os.path.dirname(os.path.abspath(__file__))   # write outputs next to this script

# ══════════════════════════════════════════════════════════════════════════════
# PROJECT PARAMETERS — edit this block to configure a different site / load case
# (WATER_DEPTH, MOORING_MBL and stage durations come from project_config.py)
# ══════════════════════════════════════════════════════════════════════════════

# Design sea state (ULS / 50-yr extreme)
WAVE_HS         = 5.5        # m   significant wave height
WAVE_TP         = 14.0       # s   spectral peak period
WAVE_DIRECTION  = 0.0        # deg (waves travelling in +X direction)
WIND_SPEED      = 18.0       # m/s (10-min mean)
WIND_DIRECTION  = 180.0      # deg (wind from south, travelling north)
CURRENT_SPEED   = 0.8        # m/s (near-surface, uniform with depth)
CURRENT_DIR     = 315.0      # deg

# Mooring geometry (3-leg spread catenary, symmetric about platform)
# Sized for a clear catenary shape: straight-line fairlead→anchor ≈ 568 m,
# total length 660 m → ~90 m slack → modest seabed laydown near the anchor.
FAIRLEAD_RADIUS =   45.0     # m   horizontal offset of fairlead from hull centre
FAIRLEAD_DEPTH  =  -20.0     # m   fairlead depth below WL (negative = below)
ANCHOR_RADIUS   =  600.0     # m   horizontal offset of anchor from hull centre
MOORING_LENGTH  =  660.0     # m   total laid chain length per leg

# Dynamic cable geometry (global coordinates)
# Sized for a visible lazy-wave shape: straight-line hang-off→touchdown ≈ 427 m,
# total length 480 m → ~50 m slack distributed across sag / hog bends.
CABLE_HANGOFF_X = -35.0      # m   I-tube exit on hull
CABLE_HANGOFF_Z = -15.0      # m   depth of hang-off point below WL
CABLE_SEABED_X  = -420.0     # m   J-tube entry on seabed

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
MOORING_HEADINGS = [30.0, 150.0, 270.0]   # degrees (global azimuth from +X)

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
