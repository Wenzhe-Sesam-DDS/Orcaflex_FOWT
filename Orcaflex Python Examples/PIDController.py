"""
This module is an example Python external function for use with OrcaFlex.
This example implements a PID controller (Proportional, Integral, Differential)
that is used to model a heave-compensated winch. For details see
'External Function Examples.pdf' in the same folder as this file, and see the
OrcFxAPI documentation OrcFxAPIHelp.exe (in the contents look for 'External
Functions' and 'Python Interface').
"""

import json


class PIDstate(object):
    def __init__(self):
        self.valid = False
        self.time = -OrcFxAPI.OrcinaInfinity()
        self.signal = 0.0
        self.iedt = 0.0
        self.dedt = 0.0

    def getStateAttributes(self):
        return {
            "valid": self.valid,
            "time": self.time,
            "signal": self.signal,
            "iedt": self.iedt,
            "dedt": self.dedt,
        }

    def setStateAttributes(self, attributes):
        self.valid = attributes["valid"]
        self.time = attributes["time"]
        self.signal = attributes["signal"]
        self.iedt = attributes["iedt"]
        self.dedt = attributes["dedt"]


class PIDController(object):
    def Initialise(self, info):
        # In the Calculate() method we'll need to ask OrcaFlex for the value of
        # our controlled variable. To do this we'll need an OrcFxAPI.Period to say
        # we want the value 'now':
        self.periodNow = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)

        # And we'll need an ObjectExtra saying we want the value at the origin
        # of the controlled object:
        self.ObjectExtra = OrcFxAPI.ObjectExtra()
        self.ObjectExtra.RigidBodyPos = (0.0, 0.0, 0.0)

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

        # Name of model object whose result variable is to be controlled:
        self.ControlledObject = info.Model[GetParam("ControlledObject")]
        # The result variable of that object to be controlled. This must be
        # one of the results available for the ControlledObject on the results
        # form in OrcaFlex:
        self.ControlledVariable = GetParam("ControlledVariable")
        # The target value for that controlled variable. Its units are those of
        # that controlled variable in the OrcaFlex model:
        self.TargetValue = GetFloatParam("TargetValue", 0.0)
        # The constants of the PID controller:
        self.k0 = GetFloatParam("k0", 0.0)  # constant part
        self.kP = GetFloatParam("kP", 0.0)  # scaling constant for the proportional part
        self.kI = GetFloatParam("kI", 0.0)  # scaling constant for the integral part
        self.kD = GetFloatParam("kD", 0.0)  # scaling constant for the differential part
        # If no value of ControlStartTime is specified then default to -Infinity,
        # so that we activate control at the start of the simulation:
        self.ControlStartTime = GetFloatParam("ControlStartTime", float("-inf"))
        # And default to not limiting the control variable:
        self.MinValue = GetFloatParam("MinValue", float("-inf"))
        self.MaxValue = GetFloatParam("MaxValue", float("+inf"))

        # If info.StateData is not None then we have been called when loading
        # a simulation, so we need to restore the controller state
        # to what our StoreState() method saved when the simulation was stored:
        self.prev = PIDstate()
        self.now = PIDstate()
        if info.StateData:
            state = json.loads(info.StateData)
            self.now.setStateAttributes(state["now"])
            self.prev.setStateAttributes(state["prev"])
        else:
            # This is a new simulation, so initialise the controller state:
            self.prev.iedt = GetFloatParam("Initial e/D", 0.0)
            self.now.dedt = GetFloatParam("Initial De", 0.0)

        print("Initialised OK.")

    def Calculate(self, info):
        # Don't start control until the specified time:
        if info.SimulationTime < self.ControlStartTime:
            return

        # If this is a new time step, and not the first, then step self.now back
        # to become our new self.prev:
        if info.NewTimeStep and self.now.valid:
            self.prev.time = self.now.time
            self.prev.signal = self.now.signal
            self.prev.iedt = self.now.iedt
            self.prev.dedt = self.now.dedt
            self.prev.valid = True

        # Get the state values now:
        self.now.time = info.SimulationTime
        self.now.signal = self.ControlledObject.TimeHistory(
            self.ControlledVariable,
            self.periodNow,  # set up in Initialise() method to give the value 'now'
            self.ObjectExtra,  # set up in Initialise() method
        )[
            0
        ]  # TimeHistory returns an array, which in this case contains just 1 item, the value now
        self.now.iedt = self.prev.iedt
        self.now.valid = True

        e = self.TargetValue - self.now.signal
        if self.prev.valid:
            prev_e = self.TargetValue - self.prev.signal
            dt = self.now.time - self.prev.time
            self.now.dedt = (e - prev_e) / dt
            self.now.iedt += dt * (e + prev_e) / 2.0
            print(f"t = {self.now.time}, e = {e}, dedt = {self.now.dedt}, iedt = {self.now.iedt}")

        info.Value = self.kP * e + self.kI * self.now.iedt + self.kD * self.now.dedt + self.k0
        # Keep the value within the specified limits (if any):
        info.Value = max(self.MinValue, min(info.Value, self.MaxValue))

    def StoreState(self, info):
        # The simulation is being stored, so we need to store our controlled state
        # to the simulation file so that when the simulation is re-loaded our
        # Initialise() method can restore to the same state. We use the built json module to get
        # the controller state into a form suitable for putting into info.StateData,
        # which OrcaFlex will store in the simulation file for us:
        state = {
            "now": self.now.getStateAttributes(),
            "prev": self.prev.getStateAttributes(),
        }
        info.StateData = json.dumps(state)
