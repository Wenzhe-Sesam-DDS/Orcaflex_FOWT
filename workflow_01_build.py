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

Public API
  build(params: dict) -> OrcFxAPI.Model
      Build a fully configured (but un-solved) model from a params dict.

Standalone CLI: builds the model with project_config defaults and saves
  testModel.dat + testModel.yml next to this file.
"""

import math
import os

import OrcFxAPI

from project_config import MOORING_HEADINGS, params_with_defaults

HERE = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════════════════════
# OC4-DeepCwind semi-sub visual geometry (constants from Robertson et al. 2014)
# ══════════════════════════════════════════════════════════════════════════════
OC4_COL_OFFSET_R = 40.868   # m  radius: platform centre → offset column centre
OC4_DRAFT        = 20.0     # m  platform draft
OC4_FREEBOARD    = 12.0     # m  column height above waterline
OC4_CENTRAL_D    =  6.5     # m  central column outer diameter
OC4_OFFSET_COL_D = 12.0     # m  upper offset column outer diameter
OC4_BASE_D       = 24.0     # m  base column outer diameter
OC4_BASE_H       =  6.0     # m  base column height
OC4_UPPER_COL_H  = OC4_DRAFT + OC4_FREEBOARD - OC4_BASE_H   # 26 m


def _add_cylinder(model, platform, name, cx, cy, z_bottom, height, diameter):
    """Create a cylindrical Shape attached to the Platform vessel."""
    s = model.CreateObject(OrcFxAPI.ObjectType.Shape, name)
    s.SetData("Connection",    0, platform.Name)
    s.SetData("Shape",         0, "Cylinder")
    s.SetData("OriginX",       0, cx)
    s.SetData("OriginY",       0, cy)
    s.SetData("OriginZ",       0, z_bottom + height / 2.0)
    s.SetData("Length",        0, height)
    s.SetData("OuterDiameter", 0, diameter)
    s.SetData("InnerDiameter", 0, 0.0)
    return s


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════
def build(params: dict) -> OrcFxAPI.Model:
    """Build a fully configured OrcaFlex model from a params dict.

    The model is *not* solved; call CalculateStatics() / RunSimulation()
    yourself (see workflow_02_run.py).
    """
    p = params_with_defaults(params)

    # ── 1. MODEL AND GENERAL SETTINGS ────────────────────────────────────────
    model = OrcFxAPI.Model()
    model.general.StageDuration = p["buildup_duration"], p["analysis_duration"]

    # ── 2. ENVIRONMENT ───────────────────────────────────────────────────────
    env = model.environment
    env.WaterDepth                  = p["water_depth"]
    env.WaveType                    = "JONSWAP"
    env.WaveHs                      = p["wave_hs"]
    env.WaveTp                      = p["wave_tp"]
    env.WaveDirection               = p["wave_direction"]
    env.UserSpecifiedRandomWaveSeeds = "Yes"
    env.WaveSeed                    = int(p["wave_seed"])

    env.WindType      = "Constant"
    env.WindSpeed     = p["wind_speed"]
    env.WindDirection = p["wind_direction"]

    env.RefCurrentSpeed     = p["current_speed"]
    env.RefCurrentDirection = p["current_dir"]

    # ── 3. PLATFORM (hull) ───────────────────────────────────────────────────
    # NOTE: this Vessel uses the OrcaFlex default VesselType (no RAOs, no wind
    # / current drag). For a representative FOWT, assign a project-specific
    # VesselType built from WAMIT / AQWA output. See README.md.
    platform = model.CreateObject(OrcFxAPI.ObjectType.Vessel, "Platform")

    _add_cylinder(model, platform, "Shape_CentralColumn", 0.0, 0.0,
                  z_bottom=-OC4_DRAFT,
                  height=OC4_DRAFT + OC4_FREEBOARD,
                  diameter=OC4_CENTRAL_D)

    for i, hdg in enumerate(MOORING_HEADINGS):
        rad = math.radians(hdg)
        cx  = OC4_COL_OFFSET_R * math.cos(rad)
        cy  = OC4_COL_OFFSET_R * math.sin(rad)
        _add_cylinder(model, platform, f"Shape_OffsetColumn{i+1}", cx, cy,
                      z_bottom=-OC4_DRAFT + OC4_BASE_H,
                      height=OC4_UPPER_COL_H,
                      diameter=OC4_OFFSET_COL_D)
        _add_cylinder(model, platform, f"Shape_BaseColumn{i+1}", cx, cy,
                      z_bottom=-OC4_DRAFT,
                      height=OC4_BASE_H,
                      diameter=OC4_BASE_D)

    # ── 4. LINE TYPES ────────────────────────────────────────────────────────
    # All values are in model default units: kN, m, te (metric tonne).
    # Verify against manufacturer data sheets / project line type library.

    # R4 stud-link chain — 114 mm bar diameter
    chain = model.CreateObject(OrcFxAPI.ObjectType.LineType, "R4 Chain 114mm")
    chain.OD                = 0.311
    chain.ID                = 0.0    # solid cross-section (override default 0.25)
    chain.MassPerUnitLength = 0.303
    chain.EA                = 854000
    chain.EIx               = 0.0    # negligible chain bending stiffness
    chain.EIy               = 0.0
    chain.GJ                = 0.0

    # Dynamic HVAC export cable — 220 kV three-core (representative)
    cable_type = model.CreateObject(OrcFxAPI.ObjectType.LineType, "HVAC Cable 220kV")
    cable_type.OD                = 0.220
    cable_type.ID                = 0.0
    cable_type.MassPerUnitLength = 0.060   # > buoyancy ≈ 0.039 te/m
    cable_type.EA                = 15000
    cable_type.EIx               = 8.0     # must set both EIx and EIy
    cable_type.EIy               = 8.0

    # Buoyancy-module section — positively buoyant; creates the hog bend
    buoy_type = model.CreateObject(OrcFxAPI.ObjectType.LineType, "HVAC Cable + BuoyancyModules")
    buoy_type.OD                = 0.500
    buoy_type.ID                = 0.0
    buoy_type.MassPerUnitLength = 0.070
    buoy_type.EA                = 15000
    buoy_type.EIx               = 8.0
    buoy_type.EIy               = 8.0

    # ── 5. MOORING LINES — 3-leg spread catenary ─────────────────────────────
    for i, hdg_deg in enumerate(MOORING_HEADINGS, start=1):
        rad = math.radians(hdg_deg)
        ml  = model.CreateObject(OrcFxAPI.ObjectType.Line, f"Mooring{i}")

        ml.EndAConnection = platform.Name
        ml.EndAX          = p["fairlead_radius"] * math.cos(rad)
        ml.EndAY          = p["fairlead_radius"] * math.sin(rad)
        ml.EndAZ          = p["fairlead_depth"]

        ml.EndBX = p["anchor_radius"] * math.cos(rad)
        ml.EndBY = p["anchor_radius"] * math.sin(rad)
        ml.EndBZ = -p["water_depth"]

        ml.LineType            = chain.Name,
        ml.Length              = p["mooring_length"],
        ml.TargetSegmentLength = 10.0,

        per = p["mooring_per_line"][i - 1]
        ml.EndAAzimuth     = per["enda_azimuth"]
        ml.EndADeclination = per["enda_declination"]
        ml.EndAGamma       = per["enda_gamma"]
        ml.EndBAzimuth     = per["endb_azimuth"]
        ml.EndBDeclination = per["endb_declination"]
        ml.EndBGamma       = per["endb_gamma"]
        ml.LayAzimuth      = per["lay_azimuth"]
        ml.AsLaidTension   = per["as_laid_tension"]

    # ── 6. DYNAMIC EXPORT CABLE — 3-section lazy-wave ────────────────────────
    cable = model.CreateObject(OrcFxAPI.ObjectType.Line, "ExportCable")
    cable.EndAConnection = platform.Name
    cable.EndAX          = p["cable_hangoff_x"]
    cable.EndAY          = 0.0
    cable.EndAZ          = p["cable_hangoff_z"]

    cable.EndBX = p["cable_seabed_x"]
    cable.EndBY = 0.0
    cable.EndBZ = -p["water_depth"]

    cable.LineType            = cable_type.Name, buoy_type.Name, cable_type.Name
    cable.Length              = 150.0, 120.0, 210.0
    cable.TargetSegmentLength = 5.0, 3.0, 5.0

    cable.EndAAzimuth     = p["cable_enda_azimuth"]
    cable.EndADeclination = p["cable_enda_declination"]
    cable.EndAGamma       = p["cable_enda_gamma"]
    cable.EndBAzimuth     = p["cable_endb_azimuth"]
    cable.EndBDeclination = p["cable_endb_declination"]
    cable.EndBGamma       = p["cable_endb_gamma"]
    cable.LayAzimuth      = p["cable_lay_azimuth"]
    cable.AsLaidTension   = p["cable_as_laid_tension"]

    return model


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    params = params_with_defaults()
    model  = build(params)

    print("Objects in model:")
    for obj in model.objects:
        print(f"  {obj}")

    dat_path = os.path.join(HERE, "testModel.dat")
    yml_path = os.path.join(HERE, "testModel.yml")
    model.SaveData(dat_path)
    model.SaveData(yml_path)
    print(f"\nModel saved: {dat_path}")
    print(f"             {yml_path}")
    print("Next step: run workflow_02_run.py")


if __name__ == "__main__":
    main()
