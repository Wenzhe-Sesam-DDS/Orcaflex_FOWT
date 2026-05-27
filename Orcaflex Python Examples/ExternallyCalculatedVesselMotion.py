"""
This module gives a simple example of using Python to apply externally-calculated
motion to a vessel in OrcaFlex. See the comments below, and for further information
see the 'External Function Examples.doc' in the same folder as this file, and see
the OrcFxAPI documentation OrcFxAPIHelp.exe (in the contents look for 'External
Functions' and 'Python Interface').
"""

from math import radians, sin, cos

# The following function returns the orientation matrix corresponding to specified
# Euler angles (Rx, Ry, Rz), in radians:


def OrientationFromRxRyRzAngles(RxRyRzAnglesInRadians):
    # Vessel primary motion rotations (Rx,Ry,Rz) are applied in the 'reverse'
    # order Rz, Ry, Rx. This code returns the resulting orientation matrix:
    S1, S2, S3 = map(sin, RxRyRzAnglesInRadians)
    C1, C2, C3 = map(cos, RxRyRzAnglesInRadians)
    # We could use a list for the orientation matrix, with the row items
    # being lists or tuples, but for simplicity we'll just use tuples here:
    return (
        (
            +C2 * C3,
            +C2 * S3,
            -S2,
        ),  # components in global axes directions, of unit vector in vessel x-axis direction
        # components in global axes directions, of unit vector in vessel y-axis direction
        (-C1 * S3 + S1 * S2 * C3, +C1 * C3 + S1 * S2 * S3, +S1 * C2),
        # components in global axes directions, of unit vector in vessel z-axis direction
        (+S1 * S3 + C1 * S2 * C3, -S1 * C3 + C1 * S2 * S3, +C1 * C2),
    )


# This class is the external function for use in OrcaFlex:


class ExternallyCalculatedVesselMotion(object):
    def Initialise(self, info):
        # We'll start from the info.StructValue.Position and info.StructValue.Orientation
        # given by OrcaFlex, so leave those unchanged; they will be the Initial Position
        # and Initial Orientation specified on the vessel data form. But we'll start
        # from stationary in that position:
        info.StructValue.Velocity = (0.0, 0.0, 0.0)
        info.StructValue.Acceleration = (0.0, 0.0, 0.0)
        info.StructValue.AngularVelocity = (0.0, 0.0, 0.0)
        info.StructValue.AngularAcceleration = (0.0, 0.0, 0.0)

        # Note the initial position and Euler angles, so that we can use then in
        # the Calculate() method below, to give continuity of position and motion:
        self.InitialPosition = info.StructValue.Position
        self.InitialEulerAnglesInRadians = (
            radians(info.ModelObject.InitialHeel),
            radians(info.ModelObject.InitialTrim),
            radians(info.ModelObject.InitialHeading),
        )

    # The external function class needs the Calculate() method, which
    # calculates the motion and returns it in info.StructValue:
    def Calculate(self, info):
        # In this example, during the build-up period (-ve simulation time)
        # we'll leave the vessel position and motion as specified in OrcaFlex.
        # So we only modify info.StructValue once time zero has been reached,
        # and in this example we just use simple sinusoidal motion:
        t = info.SimulationTime
        if t >= 0.0:
            # The vessel motion must NOT be changed within a single time step,
            # so we should only update it if this is a new time step:
            if info.NewTimeStep:
                # Translational motion:
                # OrcaFlex passes info.StructValue containing lists, so components
                # can be set individually ..
                info.StructValue.Position[0] = self.InitialPosition[0] + 30.0 * (1.0 - cos(0.1 * t))
                info.StructValue.Position[1] = self.InitialPosition[1] + 15.0 * (1.0 - cos(0.05 * t))
                info.StructValue.Position[2] = self.InitialPosition[2] + 1.5 * (1.0 - cos(0.15 * t))
                # .. but they can alternatively be returned as a new tuple ..
                info.StructValue.Velocity = (  # = derivative of Position:
                    30.0 * 0.1 * sin(0.1 * t),
                    15.0 * 0.05 * sin(0.05 * t),
                    1.5 * 0.15 * sin(0.15 * t),
                )
                # .. or as a new list:
                info.StructValue.Acceleration = (  # = derivative of Velocity:
                    30.0 * (0.1**2) * cos(0.1 * t),
                    15.0 * (0.05**2) * cos(0.05 * t),
                    1.5 * (0.15**2) * cos(0.15 * t),
                )

                # Rotational motion:
                EulerAnglesInRadians = (
                    self.InitialEulerAnglesInRadians[0] + 0.07 * (1.0 - cos(0.15 * t)),  # = Rx
                    self.InitialEulerAnglesInRadians[1] + 0.05 * (1.0 - cos(0.1 * t)),  # = Ry
                    self.InitialEulerAnglesInRadians[2] + 0.25 * (1.0 - cos(0.05 * t)),  # = Rz
                )
                info.StructValue.Orientation = OrientationFromRxRyRzAngles(EulerAnglesInRadians)
                # AngularVelocity = derivative of EulerAnglesInRadians:
                info.StructValue.AngularVelocity = (
                    0.07 * 0.15 * sin(0.15 * t),
                    0.05 * 0.1 * sin(0.1 * t),
                    0.25 * 0.05 * sin(0.05 * t),
                )
                # AngularAcceleration = derivative of AngularVelocity:
                info.StructValue.AngularAcceleration = (
                    0.07 * (0.15**2) * cos(0.15 * t),
                    0.05 * (0.1**2) * cos(0.1 * t),
                    0.25 * (0.05**2) * cos(0.05 * t),
                )

    # def StoreState(self, info):
    # For this example we don't have to store state data, so this method is not needed
