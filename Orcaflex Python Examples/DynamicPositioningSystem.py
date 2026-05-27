"""
This module is an example Python external function for use with OrcaFlex.
For details see 'External Function Examples.pdf' in the same folder as this file,
and see the OrcFxAPI documentation OrcFxAPIHelp.exe (in the contents look for
'External Functions' and 'Python Interface').
"""


class ThrusterData(object):
    # This class is used to store and share the control parameters
    # and the resulting thruster load:
    def __init__(self):
        # These constants are defined in the vessel's external function parameters
        # in the OrcaFlex model:
        self.TargetX = 0.0
        self.TargetY = 0.0
        self.TargetHeading = 0.0
        self.kf = 0.0
        self.km = 0.0
        # The thruster load:
        self.ForceX = 0.0
        self.ForceY = 0.0
        self.MomentZ = 0.0


class Thruster(object):
    def Initialise(self, info):
        # In the Calculate() method we ask OrcaFlex for the vessel heading, and
        # to do this we'll need an OrcFxAPI.Period to say we want the value 'now':
        self.periodNow = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)

        # Separate instances of this class will be created and called for each use
        # of the external function in the OrcaFlex model. So in this example there
        # will be separate Thruster objects for the X, Y and Z components of load.
        # They work together, sharing data in info.Workspace. This is a dictionary
        # shared by all external functions used in this OrcaFlex model, so we
        # store our working data under a key that keeps it specific to this vessel
        # and to this thruster class (in case the vessel also uses another Python
        # external function):
        self.WorkspaceKey = info.ModelObject.Name + "Thruster"

        # Create our shared working data if it doesn't already exist:
        if self.WorkspaceKey not in info.Workspace:
            # We've not found working data, so this is the first call for this
            # OrcaFlex object, so initialise thrusterData:
            thrusterData = ThrusterData()

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

            # The target position of the vessel origin, and heading of the vessel, relative to global axes:
            thrusterData.TargetX = GetFloatParam("TargetX", 0.0)
            thrusterData.TargetY = GetFloatParam("TargetY", 0.0)
            thrusterData.TargetHeading = GetFloatParam("TargetHeading", 0.0)
            # kf = force per unit distance away from the target position:
            thrusterData.kf = GetFloatParam("kf", 75.0)
            # km = moment per degree away from the target heading:
            thrusterData.km = GetFloatParam("km", 5000.0)

            # And save thrusterData in the Model Workspace dictionary:
            info.Workspace[self.WorkspaceKey] = thrusterData

    def Calculate(self, info):
        # A real thruster would probably apply forces and moments in the vessel axes
        # directions, so a local applied load would be more appropriate. But to keep
        # this example simple we implement the thruster as a global applied load,
        # i.e. returning thruster load components with respect to global axes.

        # Get our working data:
        thrusterData = info.Workspace[self.WorkspaceKey]

        # We calculate all the components of thruster load together, when the
        # first component (GlobalAppliedForceX) is requested, and then return the
        # component requested by that call and the subsequent calls (for
        # GlobalAppliedForceY and GlobalAppliedMomentZ).
        # This approach avoids repeating some things for each component, and is
        # also better for handling any interactions between components (though
        # this does not happen in this example).

        # info.DataName tells us which component, and which row in the applied loads
        # table in OrcaFlex, has been requested. In this example it will be
        # 'GlobalAppliedForceX[1]', 'GlobalAppliedForceY[1]' or 'GlobalAppliedMomentZ[1]',
        # since we only have 1 vessel applied load, and only use this class for those
        # 3 components:
        dataName = info.DataName

        # Ignore the index value in dataName by using dataName.startswith,
        # instead of testing for equality:
        if dataName.startswith("GlobalAppliedForceX"):
            # Note that if multiple applied loads were calculated by this class for the
            # same vessel, then we would need to have separate thrusterdata
            # for each applied load. This could be done by making thrusterdata
            # a list that was indexed by the applied load index value.

            # Get the instantaneous calculation data for the vessel:
            vesselData = info.InstantaneousCalculationData

            # Get the vessel heading. This could be calculated from
            # info.InstantaneousCalculationData.Orientation, but it is easier
            # (though less efficient, if speed is critical) to ask OrcaFlex for it:
            heading = info.ModelObject.TimeHistory(
                "Rotation 3", self.periodNow  # the primary motion heading result
            )[
                0
            ]  # TimeHistory returns an array, which in this case contains just 1 item, the value now

            # Calculate all the thruster load components:
            # (In reality a Note: You would probably not use "moment" here, but another X-Y "thruster" but
            # to make the example simpler, we use applied moment to maintain the vessels heading.
            thrusterData.ForceX = (thrusterData.TargetX - vesselData.Position[0]) * thrusterData.kf
            thrusterData.ForceY = (thrusterData.TargetY - vesselData.Position[1]) * thrusterData.kf
            thrusterData.MomentZ = (thrusterData.TargetHeading - heading) * thrusterData.km

            # And return the requested load component:
            info.Value = thrusterData.ForceX
        else:
            # The load components have already all been calculated,
            # so just return the requested component:
            if dataName.startswith("GlobalAppliedForceY"):
                info.Value = thrusterData.ForceY
            elif dataName.startswith("GlobalAppliedMomentZ"):
                info.Value = thrusterData.MomentZ
            else:
                raise Exception(
                    "This external function can only calculate X and Y force components"
                    + ", and Z moment component, of a global applied load."
                )


# def StoreState(self, info):
# For this example we don't have to store state data, so this method is not needed
# pass

# def Finalise(self, info):
# This method is not needed in this example, since OrcaFlex will automatically
# delete the data we have put in info.Workspace.
# This method would be needed if, for example, we had opened a file or other
# resource that needed closing again.
# pass
