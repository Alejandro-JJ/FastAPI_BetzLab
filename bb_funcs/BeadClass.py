import numpy as np
import matplotlib.pyplot as plt
from bb_funcs.tools import brute_axes_equal


class Bead:
    def __init__(self, pxvalue, coords_orig, coords_rot, rotation, SH_order, SH_table):

        self.pxvalue = pxvalue
        self.coords_orig = coords_orig
        self.coords_rot = coords_rot
        self.rotation = rotation
        self.SH_order = SH_order
        self.SH_table = SH_table
        # TO IMPLEMENT
        # self.SH_force = force
        # self.radius_map = radius_map
        # self.tension_map = tension_map
        # self.deformation = deformation (calculated in-situ)
        
    
    # Here I can add methods later for plotting and stuff
    def plotCoordsOrig(self):
        fig = plt.figure(figsize=(5,5))
        ax = fig.add_subplot(111, projection='3d')
        ax.scatter(self.coords_orig[0], self.coords_orig[1], self.coords_orig[2])
        brute_axes_equal(ax)
        plt.show()
    
    def plotTension3D(self):
        pass

    def plotTension2D(self):
        pass
    
    def plotRadius2D(self):
        pass
