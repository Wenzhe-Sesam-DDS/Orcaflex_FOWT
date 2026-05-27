"""
This module gives examples of Python external functions for use with OrcaFlex.
For details see 'External Function Examples.pdf' in the same folder as this file,
and see the OrcFxAPI documentation OrcFxAPIHelp.exe (in the contents look for
'External Functions' and 'Python Interface').
"""


class IncreasingSpeed(object):
    def Calculate(self, info):
        # All the external function methods are passed the info object,
        # which contains various useful attributes, including the
        # SimulationTime at the time of this call:
        if info.SimulationTime <= 0.0:
            # info.Value is the speed we're calculating.
            # Before time 0.0 set it to zero:
            info.Value = 0.0
        else:
            # .. but after time 0.0 make the speed rise steadily with time:
            info.Value = info.SimulationTime / 10.0


# ==============================================================================


class WindProportionalSpeed(object):
    def Initialise(self, info):
        # Initialise our parameters:
        self.meanCurrentSpd = 0.45
        self.windFactor = 0.05
        # And set self.period to be an OrcFxAPI.Period object that is set to
        # pnInstantaneousValue (i.e. 'now'), ready for use in the Calculate method:
        self.period = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)

    def Calculate(self, info):
        # The wind speed doesn't vary within a time step, and info.Value is
        # preseved by OrcaFlex between calls, so we only need to update
        # info.Value when it's a new time step:
        if info.NewTimeStep:
            # Get the model's environment object:
            environment = info.Model.environment

            # .. and use it to get the windSpeed 'now', which we specify using the
            # period parameter of the TimeHistory method. The objectExtra parameter
            # specifies the position at which we want the wind speed, but wind speed
            # is position-independent in OrcaFlex so the position we give doesn't matter.
            # TimeHistory returns a tuple, even though in this case there's only 1 value,
            # so we have to index it [0] to get the value itself:
            windSpeed = environment.TimeHistory("Wind Speed", self.period, info.ObjectExtra)[0]

            # print the windSpeed, so we see it in the External Function Output window
            # in OrcaFlex, and then use it to set the current speed:
            print(windSpeed)
            info.Value = self.meanCurrentSpd + self.windFactor * windSpeed


# ==============================================================================


class MovingAverageSpeed(object):
    def Initialise(self, info):
        self.period = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)
        self.meanCurrentSpd = 0.45
        self.windFactor = 0.05

        # Override the initial value specified on the variable data form,
        # so that we always start from the meanCurrentSpd:
        info.Value = self.meanCurrentSpd

        # Initialise the number of time steps we're going to time-average over:
        self.numAveragedTimeSteps = 20

        # If this call is when a part-run simulation is re-opened and continued
        # then info.StateData will exist and contain the recentWindSpeedHistory
        # that we stored in it when the simulation was saved (see StoreState below),
        # so we use it to initialse recentWindSpeedHistory back to what is was
        # when the simulation was saved:
        if info.StateData:
            # Use the Python json module to unpack the data that's
            # come back from the simulation file:
            import json

            self.recentWindSpeedHistory = json.loads(info.StateData)
        else:
            # But if this call is at the start of a simulation then info.StateData
            # is None, so we should initialse recentWindSpeedHistory to start empty:
            self.recentWindSpeedHistory = []

    def Calculate(self, info):
        if info.NewTimeStep:
            WindSpeed = info.Model.environment.TimeHistory("Wind Speed", self.period, info.ObjectExtra)[0]

            # To time-average the wind speed, add this latest windSpeed to our
            # windSpeedHistory list:
            self.recentWindSpeedHistory.append(WindSpeed)
            # .. and only keep the most recent numAveragedTimeSteps values:
            if len(self.recentWindSpeedHistory) > self.numAveragedTimeSteps:
                del self.recentWindSpeedHistory[0]

            # Calculate the average of the most recent wind speed values:
            averageWindSpeed = sum(self.recentWindSpeedHistory) / len(self.recentWindSpeedHistory)
            # .. and use that to determine the current speed:
            info.Value = self.meanCurrentSpd + self.windFactor * averageWindSpeed

    def StoreState(self, info):
        # This method is called when a simulation is saved. It enables us to save our
        # recentWindSpeedHistory in the simulation file, by putting it into info.StateData,
        # so that it can be restored by the code in the Initialise method above
        # if the simulation is resumed later.
        # We use the Python json module to convert the windSpeedHistory
        # into a form suitable for storing in the simulation file:
        import json

        info.StateData = json.dumps(self.recentWindSpeedHistory)


# ==============================================================================


import math


def GetVector(magnitude, directionDegrees):
    dirRadians = directionDegrees / 180.0 * math.pi
    return (magnitude * math.cos(dirRadians), magnitude * math.sin(dirRadians))


class MovingAverageSpeedAndDirection(object):
    def Initialise(self, info):
        # We can now be called for the current direction, as well as for the
        # current speed, and info.DataName tells us which. They are always
        # called in the order speed and then direction, so we can do all
        # the initialisation work in the speed call, and then just return
        # an Initial value for the direction call:
        if info.DataName == "RefCurrentSpeed":
            # We only need to do the initialisation that the MovingAverageSpeed
            # class did for the current speed call:
            self.period = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)
            self.meanCurrentSpd = 0.45
            self.windFactor = 0.05
            info.Value = self.meanCurrentSpd
            self.numAveragedTimeSteps = 20

            # We now also need to initialise the current direction:
            initialCurrentDirectionDegrees = 180.0
            self.initialCurrentVector = GetVector(self.meanCurrentSpd, initialCurrentDirectionDegrees)

            # Get the wind direction from the OrcaFlex wind data:
            self.windDirectionDegrees = info.Model.environment.WindDirection

            # Initialise recentWindSpeedHistory and currentDirectionDegrees,
            # either from the info.StateData from when a simulation was saved
            # or to starting values if this is a new simulation:
            if info.StateData:
                import json

                # We stored a dictionary in info.StateData when the simulation was saved:
                stateDictionary = json.loads(info.StateData)
                # .. so that we can now get both the recentWindSpeedHistory
                # and currentDirectionDegrees from it:
                self.recentWindSpeedHistory = stateDictionary["recentWindSpeedHistory"]
                info.Workspace["currentDirectionDegrees"] = stateDictionary["currentDirectionDegrees"]
            else:
                # Initialise to starting values:
                self.recentWindSpeedHistory = []
                # Save the initial current direction in the Model Workspace to be used by the
                # initialise call for RefCurrentDirection
                info.Workspace["currentDirectionDegrees"] = initialCurrentDirectionDegrees

        elif info.DataName == "RefCurrentDirection":
            # Override the Initial Value of the current direction (specified on the
            # variable data form in OrcaFlex) with the value calculated above when
            # we were initialised for the current speed:
            info.Value = info.Workspace["currentDirectionDegrees"]
        else:
            # We don't know how to handle any other values info.DataName,
            # so raise an error. this will be reported by OrcaFlex and appear
            # in the External Function Output window:
            raise Error("Unexpected dataname %s" % info.DataName)

    def Calculate(self, info):
        if info.NewTimeStep:
            if info.DataName == "RefCurrentSpeed":
                # We do the calculation in the call for current speed:

                WindSpeed = info.Model.environment.TimeHistory("Wind Speed", self.period, info.ObjectExtra)[0]
                self.recentWindSpeedHistory.append(WindSpeed)
                if len(self.recentWindSpeedHistory) > self.numAveragedTimeSteps:
                    del self.recentWindSpeedHistory[0]

                averageWindSpeed = sum(self.recentWindSpeedHistory) / len(self.recentWindSpeedHistory)

                # Calculate the average wind velocity vector, i.e. both speed and direction:
                averageWindVector = GetVector(averageWindSpeed, self.windDirectionDegrees)
                # .. and from that the current velocity vector that we want:
                currentVector = (
                    self.initialCurrentVector[0] + self.windFactor * averageWindVector[0],
                    self.initialCurrentVector[1] + self.windFactor * averageWindVector[1],
                )
                # Set the current speed to the magnitude of currentVector:
                info.Value = math.hypot(currentVector[0], currentVector[1])
                # .. and set the shared class variable currentDirectionDegrees to its direction:
                info.Workspace["currentDirectionDegrees"] = (
                    math.atan2(currentVector[1], currentVector[0]) * 180.0 / math.pi
                )  # to convert into degrees
            else:
                # The value to return for direction has already been calculated
                # in the call for current speed:
                info.Value = info.Workspace["currentDirectionDegrees"]

    def StoreState(self, info):
        # We store all the state, for both speed and direction,
        # in the call for current speed:
        if info.DataName == "RefCurrentSpeed":
            import json

            # We now need to store both recentWindSpeedHistory and currentDirectionDegrees
            # so for clarity store a dictionary containing them both:
            stateDictionary = {
                "currentDirectionDegrees": info.Workspace["currentDirectionDegrees"],
                "recentWindSpeedHistory": self.recentWindSpeedHistory,
            }
            info.StateData = json.dumps(stateDictionary)
