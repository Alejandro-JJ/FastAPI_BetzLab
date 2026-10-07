"""
Functions to segment 3D tiffs, based on pyclesperanto_prototype
"""
import pyclesperanto_prototype as cle
import numpy as np
import pyshtools as sh
import scipy
from .Tools import sphereFit, Rotate, cart2sph, SH2NP
from .StressTensor_tools import BeadSolverFromTable


def MasterSegmenter(im, timepoint=0, backg_r=20, threshold=200, spot_sigma=1, outline_sigma=1, 
                    perc_int=100):
    """
    Master Segmenter Function
    
    Many curated steps that render nice segmentations of PAA Beads inside Zebrafish
    embryos. The user has 5 main parameters to tune,explained below:
    After innumerable trials and errors, this seems like a sound code.
    All steps are absolutely necessary to achieve a proper segmentation.
    
    img_path = str, absolute path of .tif with a single channel, isotropic resolution
    back_r = float, box size for background cleaning, 10-20 is good
    threshold = HARD threshold for the whole image, probably the most critical parameter
    spot_sigma = approx size of searched blobs
    outline_sigma = tightness of segm. 1 is the desired value, any higher increases virtually the volume
    perc_int = how much percentage of the brightest segmentations we want to retain

    `im` is already a loaded numpy array (not a file path).
    """   
    # Make sure we have a GPU, simply the first one to pop up
    #cle.select_device(cle.available_device_names()[0])
    
    # Read and mount the image on the GPU
    input_gpu = cle.push(im)
    
    # Clean background
    im_background_clean = cle.top_hat_box(input_gpu, radius_x=backg_r, 
                                          radius_y=backg_r, radius_z=backg_r)
    
    # Mask with a hard threshold
    mask = cle.threshold(im_background_clean, constant=threshold)
    im_masked = im_background_clean*mask
    
    # Segment with PyCLesperanto method
    im_segmented = cle.voronoi_otsu_labeling(im_masked, spot_sigma=spot_sigma, 
                                             outline_sigma=outline_sigma)

    # Extract a certain top percentage of intensities, in case we have speckles
    intensity_map = cle.mean_intensity_map(im_background_clean, im_segmented)
    min_intensity = (100-perc_int)/100*np.amax(intensity_map)
    
    # Final product
    im_beads = cle.exclude_labels_with_map_values_out_of_range(intensity_map, im_segmented, 
                                                        minimum_value_range=min_intensity, 
                                                        maximum_value_range=np.inf)
    im_beads = cle.pull(im_beads)
    
    # Some beads statistics
    # Size takes for granted 1x1x1 um resolution, should be adapted if not
    (bead, size) = np.unique(im_beads, return_counts=True)
    bead = bead[1:]
    size = size[1:] # delete contribution from background pixel value=0
    n = len(bead)
    return im_beads, n

def ExtractSurface(im_beads, pixvalue, pxy, pz, buffer=5): # buffer should be set to 0 after debug
    """
    Given a segmented image, extract the surface corresponding
    to the body labelled with pixelvalue.
    This is useful both for SolveBead and for plotting
    Returns:
        - cropped binary image of the bead in question
        - list of coordinates, already scaled with pixel size AND centered
    
    Cropping buffer should better set to zero to avoid problems at the image edge
    If is guaranteed that we always have enough edge, can be increased and cropped ims 
    will have a bit of a frame
    """
    coords = np.where(im_beads==pixvalue) # not scaled yet, just to crop
    lim_z = [np.min(coords[0])-buffer, np.max(coords[0])+buffer]
    lim_y = [np.min(coords[1])-buffer, np.max(coords[1])+buffer]
    lim_x = [np.min(coords[2])-buffer, np.max(coords[2])+buffer]
    
    # cropped, masked, segmented and binary versions 
    crop = im_beads[lim_z[0]:lim_z[1], lim_y[0]:lim_y[1], lim_x[0]:lim_x[1]]
    binary_crop = (crop==pixvalue)
    
    surface = cle.detect_label_edges(binary_crop)
    binary_surface = cle.pull(surface).astype(bool)
    
    # Now we get the coords from the crop
    # These are still the original coords before rotation
    y = np.where(binary_surface==1)[0] * pz
    z = -np.where(binary_surface==1)[1]  * pxy 
    x = np.where(binary_surface==1)[2] * pxy
    
    # Fit a sphere to the cloud, find center and displace cloud to the origin
    radius,C = sphereFit(x, y, z)
    x, y, z = x - C[0], y - C[1], z - C[2]
    
    return x, y, z, binary_surface


def GetC20(angles, coords, ExpDegree=5):
    '''
    Returns the C20 component of the structure defined by coords
    The coords have been already scaled at this point, after ExtractSurface()
    Takes the coordinates (scaled and centered)
    '''
    rot_x=angles[0]
    rot_y=angles[1]   
    x,y,z = coords   
    # Fit a sphere to the cloud, find center and displace cloud to the origin
#    radius,C = sphereFit(x, y, z)
#    x, y, z = x - C[0], y - C[1], z - C[2]
    
    # COORDINATES MUST HAVE BEEN CENTERED AND SCALED BEFORE
    
    # The Rotate function is written such that rotation is first in X and then in Y
    x_new, y_new, z_new = Rotate (x, y, z, rot_x, rot_y, 0)
    
    # Transform to spherical coordinates, re-format for SHTools
    lat, lon, d = cart2sph(x_new, y_new, z_new)
    lat=np.rad2deg(lat)
    lon=np.rad2deg(lon)
    lat_sh=lon
    lon_sh=lat+180
    d_sh=d
    
    # Expansion with SHTools
    SHExpansion = sh.expand.SHExpandLSQ(d_sh,lat_sh,lon_sh,ExpDegree)
    #residuo = SHExpansion[1]
    coeffs = sh.SHCoeffs.from_array(SHExpansion[0])
    table = coeffs.coeffs
    C20 = table[0,2,0]
    
    # This returns the value as it is, and optimize.minimize with look for the smallest
    return +C20



def FullC20Optimization(coords, ExpDegree=5, ignore_rot=True):
    """
    This is an improved version of BeadBuddy previous iterations
    (before 2026). In this case, we only pass the coordinates, 
    already scaled AND centered
    Here we make:
        - find optimal rotation to find orient. with minimum C20 coeff
        - apply rotation and calculate new coords
        - return new coords, coords of the fit, SHTable
    If ignore_rot==True, the bead will be analyzed as in the original pic
    If ignore_rot==False, the bead will be rotated to minimize c20 before analysis
    """
    x, y, z = coords

    rot_x_guess, rot_y_guess = 0, 0
    guess = np.array([rot_x_guess, rot_y_guess])
    output = scipy.optimize.fmin(GetC20, guess, args=(coords, ExpDegree),disp=False)

#    print('Optimal rotation for minimum C20 projection along Z axis:')
#    print('rot_x= %.2f° ; rot_y= %.2f°' % (output[0], output[1])) 
    if ignore_rot==False:
        optimal_rot_x = output[0]
        optimal_rot_y = output[1]
    else:
        optimal_rot_x = 0
        optimal_rot_y = 0
#    print(f'Ignored rotation = {ignore_rot}')
    
    # Once optimal rotation has been found, apply it
    x_new, y_new, z_new = Rotate (x, y, z, optimal_rot_x, optimal_rot_y, 0)
    coords_new = (x_new, y_new, z_new)

    # Transform to spherical coordinates, re-format for SHTools
    lat, lon, d = cart2sph(x_new, y_new, z_new)
    lat=np.rad2deg(lat)
    lon=np.rad2deg(lon)
    lat_sh=lon
    lon_sh=lat+180
    d_sh=d
    
    # Include orthonormalization norm=1=4pi
    SHExpansion=sh.expand.SHExpandLSQ(d_sh,lat_sh,lon_sh,ExpDegree)
    coeffs = sh.SHCoeffs.from_array(SHExpansion[0])
    coeffs_ortho = sh.SHCoeffs.convert(coeffs, normalization='ortho') # works!
    table = coeffs_ortho.coeffs
 
    # Recover also the coordinates of the expansion
    coords_fit = SH2NP(coeffs_ortho)

    return coords_new, coords_fit, table
    

def Analysis(seg_vol, label, Pixel_XY, Pixel_Z, ExpDegree=3, G=1000, nu=0.49, buffer=0):
    """
    The final function. Takes labelled picture and
        - Extract surface of desired bead (pixel value)
        - Rotates and Optimized C20
        
        - Run optimization (to be implemented!)
         
        - Returns coords
    """
    x, y, z, binary_surface = ExtractSurface(seg_vol, label, Pixel_XY, Pixel_Z)
    coords_new, coords_fit, table = FullC20Optimization((x, y, z), ExpDegree=ExpDegree)
    map_r_R, map_T_R = BeadSolverFromTable(table, order=ExpDegree, G_exp=G, nu_exp=nu, N_lats=50, N_lons=100)
    
    return *coords_fit, binary_surface, map_r_R, map_T_R
    

