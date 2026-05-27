"""
This module is an example Python external function for use with OrcaFlex.
For details see 'External Function Examples.pdf' in the same folder as this file,
and see the OrcFxAPI documentation OrcFxAPIHelp.exe (in the contents look for
'External Functions' and 'Python Interface').
"""

from math import copysign


class WingAngleDepthControl(object):
    def Initialise(self, info):
        # Set up an OrcFxAPI.Period that we can use in the Calculate() method
        # to ask OrcaFlex for the instantaneous buoy angle:
        self.periodNow = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)

        # Convenience functions to get values from the object's tags:
        def GetParam(paramName, default=None):
            param = info.ModelObject.tags.get(paramName, None)
            if param is None:
                if default is None:
                    raise Exception(
                        "Parameter {} is required but is not included in "
                        "the object tags.".format(paramName)
                    )
                return default
            return param

        def GetFloatParam(paramName, default=None):
            return float(GetParam(paramName, default))

        # Simulation time at which the external function should start controlling the towed fish:
        self.ControlStartsAtTime = GetFloatParam("ControlStartsAtTime", float("-inf"))
        # Depth the towed fish should 'fly' at:
        self.TargetDepth = GetFloatParam("TargetDepth")
        # Limiting angle of the wing to the horizontal:
        self.WingAngleToHorizontalMax = GetFloatParam("WingAngleToHorizontalMax")
        # Gamma angle to make wing horizontal, relative to the buoy (in degrees)
        self.WingAngleForHorizontal = GetFloatParam("WingAngleForHorizontal")
        # Factor relating wing angle to depth minus target depth (dimensionless):
        self.DepthToAngleFactor = GetFloatParam("DepthToAngleFactor")

        print(f"Initialised {info.DataSourceName}")

    def Calculate(self, info):
        # If the control has started, then calculate the wing angle required
        # and return it in info.Value:
        if info.SimulationTime <= self.ControlStartsAtTime:
            # It is too early to start control yet, so leave info.Value unchanged.
            # It will still be the Initial Value that is specified on the
            # Variable Data form in OrcaFlex.
            pass
        else:
            # Get the wing depth at this timestep from the InstantaneousCalculationData.
            # This is the Z position, which is the 3rd component Position, so it is
            # i.e. Position[2] since Python uses zero-based indices:
            wingDepth = info.InstantaneousCalculationData.Position[2]

            # Get the Buoy angle at this time step. This isn't provided in
            # info.InstantaneousCalculationData, so we have to ask OrcaFlex for it.
            # It is the instantaneous value of the 'Rotation 2' result:
            buoyAngle = info.ModelObject.TimeHistory(
                "Rotation 2",  # this OrcaFlex result is the angle we want
                self.periodNow,  # we only want the value now (periodNow was set up in Initialise() above)
            )[
                0
            ]  # the TimeHistory method returns an array, which in this case has only 1 item

            # Calculate the difference between the depth of the wing and the target depth:
            depthDifference = wingDepth - self.TargetDepth

            # Calculate the angle the wing needs to be relative to horizontal:
            wingAngleToHorizontal = self.DepthToAngleFactor * depthDifference

            # Limit the value to the maximum wing to horizontal angle allowed:
            if abs(wingAngleToHorizontal) > self.WingAngleToHorizontalMax:
                wingAngleToHorizontal = copysign(self.WingAngleToHorizontalMax, wingAngleToHorizontal)

            # return the newly-calculated wing angle
            info.Value = self.WingAngleForHorizontal - buoyAngle + wingAngleToHorizontal

            print(f"{info.ObjectExtra.WingName}: Depth={wingDepth} Angle={info.Value}")
