"""
This module is an example Python external function for use with OrcaFlex.
It demonstrates returning a custom line stress result with a radial position and
stress fators specified by the user. For details see 'External Function Examples.pdf'
in the same folder as this file, and see the OrcFxAPI documentation OrcFxAPIHelp.exe
(in the contents look for 'External Functions' and 'Python Interface').
"""

import json
import math

# Only one external result calculated by this external function
STRESS_RESULT_ID = 0


class NodeHalfSegmentData(object):
    # A helper class for storing half segment working data
    def __init__(self):
        self.curv_x_y = (0.0, 0.0)
        self.arclength = -1.0
        self.segmentIn = False


class StressFactor(object):
    def __init__(self):
        # Create a period object once in this instance for reuse later.
        self.INSTANTANEOUS_PERIOD = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)

    def Initialise(self, info):
        # Two instances of this external result are created for each line node, one for each half segment
        # - In and Out. The DataName tells us which half segment we are in which we store in a WorkingData object.
        self.WorkingData = NodeHalfSegmentData()
        self.WorkingData.segmentIn = True if info.DataName.endswith("In") else False

    def RegisterResults(self, info):
        # Pass OrcaFlex some details of the result we are calculating. The result 'ID' is used by OrcaFlex to
        # specifiy the result required when calling 'DeriveResult' below. The units code string '$S' will be
        # substituted by OrcaFlex with the stress units used by the model.
        info.ExternalResults = [{"ID": STRESS_RESULT_ID, "Name": "External Stress", "Units": "$S"}]

    def TrackCalculation(self, info):
        # Called before LogResult, this method gives the External Result instance a chance to view the value
        # for the data item, the instantaneous calculation data and update our working data. We record the
        # mid segment arclength for this node here as this information is not available in the Initialise call.
        # We also record the x and y curvature components for the half segment at this time step and record
        # this in our working data. This method is called twice for each Node at each log interval.
        wd = self.WorkingData
        nodeData = info.InstantaneousCalculationData
        if wd.arclength < 0.0:  # If the arclength in the working data has not been initialised - do so.
            wd.arclength = nodeData.MidSegArcLengthIn if wd.segmentIn else nodeData.MidSegArcLengthOut
        wd.curv_x_y = nodeData.CurvatureIn if wd.segmentIn else nodeData.CurvatureOut

    def LogResult(self, info):
        # This method is called at each log interval, and allows us to extract or precalculate data for our
        # result and save this in the OrcaFlex log file. We use the Python module json to convert our log data
        # to a string required by OrcaFlex. Here we get the instantaneous Wall tension at this node's arclength
        # and save this with the half segment curvature data stored in or working data from the TrackCalculation call.
        wd = self.WorkingData
        oe = OrcFxAPI.oeArcLength(wd.arclength)
        tension = info.ModelObject.TimeHistory("Wall Tension", self.INSTANTANEOUS_PERIOD, oe)[0]
        info.LogData = json.dumps([tension, wd.curv_x_y])

    def DeriveResult(self, info):
        # When our external result is requested through OrcaFlex, this method is called with the log data (saved
        # in LogResult) for each log sample within the query period. First check which external result has been
        # requested, this example has only one.
        if info.ResultID == STRESS_RESULT_ID:
            # Retreive our logged data, and use the json module to convert the string back to Python types.
            logData = json.loads(info.LogData)
            tension = logData[0]
            curv_x_y = logData[1]
            # Load in the user specified parameters for the external result in the objectextra's
            # ExternalResultText property. We are also using the JSON format for this text.
            ert = json.loads(info.ObjectExtra.ExternalResultText)
            tensionStressFactor = ert["w"]
            curvatureStressFactor = ert["c"]
            theta = math.radians(ert["t"])
            # Calculate and return the stress component result to OrcaFlex
            info.Value = tensionStressFactor * tension + curvatureStressFactor * (
                curv_x_y[0] * math.sin(theta) - curv_x_y[1] * math.cos(theta)
            )
