from bb_funcs.MasterSegmenter import MasterSegmenter
from bb_funcs.BeadClass import Bead
import pyclesperanto_prototype as cle
from bb_funcs.F_C20_Optimization import C20_optimization, C20_rotation_outputs
from tqdm import tqdm



def completeAnalysis(img_path, timepoint=0, backg_r=5, threshold=100, spot_sigma=1, outline_sigma=1, 
    perc_int=100, SH_Order=3, Poisson=0.49, G=1000, pxy=1, pz=1, override_rotation=True):
    
    # Call segmentation 
    im_labelled, n, radii = MasterSegmenter(img_path, timepoint=0, backg_r=backg_r, threshold=threshold, spot_sigma=spot_sigma, outline_sigma=outline_sigma, perc_int=100)
    print('segmentation done')
    
    # For each found bead, run analysis and save data to list
    beads = {} # Dictionary instead of list allows pxvalue lookup! We avoid list 0-start
    for pxvalue in tqdm(range(1, n+1)):
        print(f'Bead {pxvalue}')
        # Mask
        masked = (im_labelled==pxvalue)*1
        beadSurface = cle.detect_label_edges(masked)
        beadSurface_binary = cle.pull(beadSurface).astype(bool)   
        # Rotate coords
        rotation = C20_optimization(beadSurface_binary, SH_Order, pxy, pz)
        if override_rotation==True:
            rotation = [0,0]
        # Get bead info after rotation
        coords_rot, coords_orig, SH_table, fit_coords = C20_rotation_outputs(rotation, beadSurface_binary, SH_Order, pxy, pz)

        # IMPLEMENT : full solution, storage
        # Save in class list
        beads[pxvalue] = Bead(pxvalue, coords_orig, coords_rot, rotation, SH_Order, SH_table)

    return beads

        
            



