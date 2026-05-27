"""
This module is an example Python external function for use with OrcaFlex, it demonstrates
defining an external result which returns a Vessel's position relative to another model object
specified by the user. For details see 'External Function Examples.pdf' in the same folder
as this file, and see the OrcFxAPI documentation OrcFxAPIHelp.exe (in the contents look for
'External Functions' and 'Python Interface').
"""

import json

# External result ids, each result needs a unique ID number
VESSEL_OFFSET_X = 0
VESSEL_OFFSET_Y = 1
VESSEL_OFFSET_Z = 2

# Helper class used for storing the vessel body position : clearance object position data
# specified in the external function parameters


class ObjectBodyPositions(object):
    def __init__(self, objectName, vesselOE, objectOE):
        self.objectName = objectName
        self.vesselOE = vesselOE
        self.objectOE = objectOE


# The external function class


class VesselClearance(object):
    def __init__(self):
        # Create the query period object once only
        self.INSTANTANEOUS_PERIOD = OrcFxAPI.Period(OrcFxAPI.pnInstantaneousValue)

    def Initialise(self, info):
        # Read the tags which specifies the vessel and object body positions we want to log. We search for
        # tags that end with the text 'Clearance'. The value of the tag a JSON representation of a dictionary
        # of vessel and object. The name prefix is used as a key when requesting the result later.
        self.clearanceObjects = {}
        tags = info.ModelObject.tags
        for name in tags:
            if name.endswith("Clearance"):
                clearanceName = name[: -len("Clearance")]
                # Convert the JSON back into a Python dictionary
                objs = json.loads(tags[name])
                objectName = objs["Object"]
                # Convert the body positions into OrcaFlex ObjectExtra instances, if no position is specified
                # then the default is (0.0, 0.0, 0.0)
                vesselPos = OrcFxAPI.oeVessel(objs.get("VesselPos", [0, 0, 0]))
                objectPos = OrcFxAPI.oeVessel(objs.get("ObjectPos", [0, 0, 0]))
                self.clearanceObjects[clearanceName] = ObjectBodyPositions(objectName, vesselPos, objectPos)

    def RegisterResults(self, info):
        # Register the result IDs and names with OrcaFlex. See the OrcFxAPI help for details. 'LL' will be
        # substituted with the length units used in the Model.
        info.ExternalResults = [
            {"ID": VESSEL_OFFSET_X, "Name": "Vessel Clearance X", "Units": "LL"},
            {"ID": VESSEL_OFFSET_Y, "Name": "Vessel Clearance Y", "Units": "LL"},
            {"ID": VESSEL_OFFSET_Z, "Name": "Vessel Clearance Z", "Units": "LL"},
        ]

    def LogResult(self, info):
        def getPositionValues(obj, oe):
            # Helper function to extract Global X, Y, and Z position for an object.
            values = []
            for var in ("X", "Y", "Z"):
                values.append(obj.TimeHistory(var, self.INSTANTANEOUS_PERIOD, oe)[0])
            return values

        # We only need to log this data once per log interval, so test for the applied
        # force x data item and ignore other calls
        if info.DataName.startswith("GlobalAppliedForceX"):
            # Store the log data as a dictionary, keyed by the name given to the body
            # position combination in the external function parameters.
            logData = {}
            for clearanceName, objectDetails in self.clearanceObjects.items():
                vesselPos = getPositionValues(info.ModelObject, objectDetails.vesselOE)
                otherPos = getPositionValues(info.Model[objectDetails.objectName], objectDetails.objectOE)
                logData[clearanceName] = (vesselPos, otherPos)
            # We need to return the log data as a string to OrcaFlex, use the json module to do this.
            info.LogData = json.dumps(logData)

    def DeriveResult(self, info):
        logData = json.loads(info.LogData)
        # Get the name of the body position set we need to use from the ObjectExtra in OrcaFlex query.
        clearanceResult = info.ObjectExtra.ExternalResultText
        objPositions = logData.get(clearanceResult, None)
        if objPositions is None:
            info.Value = OrcFxAPI.OrcinaNullReal()
            return

        vesselPos = objPositions[0]
        objectPos = objPositions[1]

        # Check which result ID has been requested and return the appropriate position offset.
        index = info.ResultID - VESSEL_OFFSET_X
        info.Value = vesselPos[index] - objectPos[index]
