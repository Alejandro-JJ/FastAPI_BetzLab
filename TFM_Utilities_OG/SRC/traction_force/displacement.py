# Libraries
import numpy as np
import math
import scipy as sc # type: ignore
import itk
import os
from skimage.registration import phase_cross_correlation
from scipy.signal import fftconvolve
import shutil
import pathlib

def normxcorr2(template, image, mode="full"):

    """
    Input arrays should be floating point numbers.
    :param template: N-D array, of template or filter you are using for cross-correlation.
    Must be less or equal dimensions to image.
    Length of each dimension must be less than length of image.
    :param image: N-D array
    :param mode: Options, "full", "valid", "same"
    full (Default): The output of fftconvolve is the full discrete linear convolution of the inputs. 
    Output size will be image size + 1/2 template size in each dimension.
    valid: The output consists only of those elements that do not rely on the zero-padding.
    same: The output is the same size as image, centered with respect to the ‘full’ output.
    :return: N-D array of same dimensions as image. Size depends on mode parameter.
    """
    ########################################################################################
    # Author: Ujash Joshi, University of Toronto, 2017                                     #
    # Based on Octave implementation by: Benjamin Eltzner, 2014 <b.eltzner@gmx.de>         #
    # Octave/Matlab normxcorr2 implementation in python 3.5                                #
    # Details:                                                                             #
    # Normalized cross-correlation. Similiar results upto 3 significant digits.            #
    # https://github.com/Sabrewarrior/normxcorr2-python/master/norxcorr2.py                #
    # http://lordsabre.blogspot.ca/2017/09/matlab-normxcorr2-implemented-in-python.html    #
    ########################################################################################

    # If this happens, it is probably a mistake
    if np.ndim(template) > np.ndim(image) or \
            len([i for i in range(np.ndim(template)) if template.shape[i] > image.shape[i]]) > 0:
        print("normxcorr2: TEMPLATE larger than IMG. Arguments may be swapped.")

    template = template - np.mean(template)
    image = image - np.mean(image)

    a1 = np.ones(template.shape)
    # Faster to flip up down and left right then use fftconvolve instead of scipy's correlate
    ar = np.flipud(np.fliplr(template))
    out = fftconvolve(image, ar.conj(), mode=mode)
    
    image = fftconvolve(np.square(image), a1, mode=mode) - \
            np.square(fftconvolve(image, a1, mode=mode)) / (np.prod(template.shape))

    # Remove small machine precision errors after subtraction
    image[np.where(image < 0)] = 0

    template = np.sum(np.square(template))
    with np.errstate(divide='ignore',invalid='ignore'): 
        out = out / np.sqrt(image * template)

    # Remove any divisions by 0 or very close to 0
    out[np.where(np.logical_not(np.isfinite(out)))] = 0
    
    return out
# Functions
def normxcorr2_leg(img, temp, fft=False):
    """Calculates map of normalized correlation coefficients
       for an image and a template image. The borders are
       patted with zero values.

    Args:
        img (numpy.ndarray): Image to compare template against.
        temp (numpy.ndaray): Template; needs to be smaller than img.
        fft (bool): Wether to utilize fast fourier or not. Will not be normalized

    Returns:
      result (numpy.ndarray): Correlation map; Correlation coefficients for each 
      area surrounding a position of same size as the template.
    """
    
    if False in [np.shape(img)[i] > np.shape(temp)[i] for i in range(2)]:
        raise IndexError(
            f"Expected Image to be bigger than template, got img:{np.shape(img)}; temp:{np.shape(temp)}"
        ) 
    
    # Define dimensions
    result = np.zeros((img.shape[0], img.shape[1]))
    
    u_lim = [int(temp.shape[1]/2), int(img.shape[1]-temp.shape[1]/2)]
    v_lim = [int(temp.shape[0]/2), int(img.shape[0]-temp.shape[0]/2)]
    
    # Calculate correlation map
    if fft:
        f2 = sc.fft.fft2(temp-np.mean(temp)).conj()
    else:
        f2 = temp-np.mean(temp)
        
    for u in range(u_lim[0], u_lim[1]):
        for v in range(v_lim[0], v_lim[1]):
            
            ## Get region under template
            y_lim = [v-math.floor(temp.shape[0]/2), v+math.ceil(temp.shape[0]/2)]
            x_lim = [u-math.floor(temp.shape[1]/2), u+math.ceil(temp.shape[1]/2)]
            
            image_under_temp = img[y_lim[0]:y_lim[1], x_lim[0]:x_lim[1]]
            
            if fft:
                f1 = sc.fft.fft2(image_under_temp)
                result[v][u] = sc.fft.ifft2(f1*f2)[0][0].real
            else:   
                f1 = image_under_temp-np.mean(image_under_temp)
                result[v][u] = np.sum(f1*f2)/(np.sqrt(np.sum(np.square(f1))*np.sum(np.square(f2))))
    
    # Remove Nans
    result = np.where(np.isnan(result), 0, result)
            
    return result


def sc_correlate(img, temp):
    """Calculates map for correlation coefficients using scipy.signal.convolve.

    Args:
        img (numpy.ndarray): Image to compare against.
        temp (numpy.ndarray): Template; needs to be smaller than img.

    Returns:
        result (numpy.ndarray): Correlation map; Correlation coefficients for each 
        area surrounding a position of same size as the template.
    """
    if False in [np.shape(img)[i] >= np.shape(temp)[i] for i in range(2)]:
        raise IndexError(
            f"Expected Image to be bigger than template, got img:{np.shape(img)}; temp:{np.shape(temp)}"
        ) 
    
    #img = (img-np.mean(img))
    #temp = (temp-np.mean(temp))
    
    #result = sc.signal.correlate(img, temp, mode="same")/np.sqrt(np.sum(img**2)*np.sum(temp**2))
    img_local = img - np.mean(img)
    temp_local = temp - np.mean(temp)
    corr = sc.signal.correlate(img_local, temp_local, mode="same")
    norm = np.sqrt(np.sum(img_local**2) * np.sum(temp_local**2))
    result = corr / norm
    
    return result

def cor_displacement(img, ref, M=32, N=32, S=8, mode="scipy"):
    """ Calculates displacement field for image in respect to reference image.
    Image and reference are divided in windows. The windows are cross corelated
    with each other to calculate how they are shifted to one another.
    
    Args:
        img (numpy.ndarray): Moving image.
        ref (numpy.ndarray): Reference image.
        M (int, optional): Size of template window in x. Defaults to 32.
        N (int, optional): Size of template window in y. Defaults to 32.
        S (int, optional): Buffer radius of search window. Defaults to 8.
        mode (str, optional): Wether to use scipy based correlation or matlab.
        
    Returns:
        results (numpy.ndarray): 2D array of displacment vectors. Index of vector correlates to
        postion at img. array([[[u,v],[...],...],[...],...])
        Shape is (int, int, 2).
        coeffs (numpy.ndarray): 2D array of correlation coefficients. Index correlates to
        position at img.
        Shape is (int, int, 2)
        coeffs (numpy.ndarray): Array containing the correlation coefficients
        for each vector.

    """
    
    results = []
    coeffs = []
    mean_coeffs = []
    
    # Loop over image
    for y in range(S, img.shape[0]-N,N-S):
        tmp_list = []
        tmp_list_coef = []
        tmp_list_mean_coef = []
        for x in range(S, img.shape[1]-M,M-S):
            ## Split image in windows
            window = img[y:y+N, x:x+M]
            
            ## Search window in arear of image window but bigger
            ref_window = ref[y-S:y+N+S, x-S:x+M+S]
            
            ## Cross Corelation
            if mode == "scipy":
                cor_map = sc_correlate(ref_window, window)
            elif mode == "matlab":
                cor_map = normxcorr2(window, ref_window)
            else:
                raise TypeError(f"Expected mode to be either 'scipy' or 'matlab'. Got {mode}.")
                       
            ## Compare correlation result with window postion
            pos_y, pos_x = np.where(cor_map==np.max(cor_map))
            if len(pos_x) == 0 or len(pos_y) == 0:
                pos_x = [cor_map.shape[1]/2, 0]
                pos_y = [cor_map.shape[0]/2, 0]
            pos_y = pos_y[0]
            pos_x = pos_x[0]
            
            ## Calculate displacement
            dif_x = cor_map.shape[1]/2 - pos_x
            dif_y = cor_map.shape[0]/2 - pos_y
            
            tmp_list.append([dif_y, dif_x])
            tmp_list_coef.append(np.max(cor_map))
            tmp_list_mean_coef.append(np.mean(cor_map))
        
        results.append(tmp_list)
        coeffs.append(tmp_list_coef)
        mean_coeffs.append(tmp_list_mean_coef)
    
    return np.array(results), np.array(coeffs), np.array(mean_coeffs)

def elastix_displacement(fixed, moving,  x_step=10, y_step=10, M=12, N=12,
                         threads=1):
    """ Cacluates displacement field utalizing elastix and bspline and rigid
    transformations for registration and tranformix. Will create an Elastix
    directory inside the working directory to store elastix files.
    Args:
        fixed (numpy.ndarray): Fixed or reference image.
        moving (numpy.ndarray): Moving image.
        x_step (int, optional): Sampling Step in x for points to be evaluated with
        transformix. Defaults to 10.
        y_step (int, optional): Sampling step y for points to be evaluated with
        transformix. Defaults to 10.
        M (int, optional): Grid Spacing x. Defaults to 32.
        N (int, optional): Grid spacing in y. Defaults to 32.
        threads(int, optional): Number of threads to run elastix registration with. Defaults to 1.

    Returns:
        numpy.ndarray: 2D array of displacment vectors. Index of vector correlates to
        postion at img. array([[[u,v],[...],...],[...],...])
        Shape is (int, int, 2).
 

    """
    if len(moving.shape) != 2 or len(fixed.shape) != 2:
        raise IndexError(
            f"fixed and moving need to be 2D; got: \nmoving: {moving.shape}\
            \nand fixed: {fixed.shape}"
            )
            
    ## Create folders
    if os.path.exists("Elastix"):
        shutil.rmtree("Elastix")
    os.makedirs("Elastix", exist_ok=True)
    
    fixed_itk = itk.GetImageFromArray(fixed)
    moving_itk = itk.GetImageFromArray(moving)
        
    # Get Parameter Maps and adjust settings
    # Get parameter maps
    pamap_rigid = itk.ParameterObject.New().GetDefaultParameterMap("rigid")
    #pamap_bspline = itk.ParameterObject.New().GetDefaultParameterMap("bspline")
    pamap_bspline = {
    # Image Types
    "FixedInternalImagePixelType": ("float",),
    "MovingInternalImagePixelType": ("float",),
    "FixedImageDimension": ("2",),  # ← Changed from 3 to 2
    "MovingImageDimension": ("2",),  # ← Changed from 3 to 2
    "UseDirectionCosines": ("true",),

    # Components
    "Registration": ("MultiResolutionRegistration",),
    "FixedImagePyramid": ("FixedSmoothingImagePyramid",),
    "MovingImagePyramid": ("MovingSmoothingImagePyramid",),
    "Interpolator": ("BSplineInterpolator",),
    "Metric": ("AdvancedMattesMutualInformation",),
    "Optimizer": ("AdaptiveStochasticGradientDescent",),
    "ResampleInterpolator": ("FinalBSplineInterpolator",),
    "Resampler": ("DefaultResampler",),
    "Transform": ("RecursiveBSplineTransform",),  # Works in 2D

    # Pyramid
    "NumberOfResolutions": ("3",),
    "ImagePyramidSchedule": ("2", "2", "2", "2", "1", "1",),  # ← 2D: x,y only

    # Transform
    "FinalGridSpacingInVoxels": (f"{M}", f"{N}"),  # ← Removed z-component
    "GridSpacingSchedule": ("4.0", "4.0", "2.0", "2.0", "1.0", "1.0"),  # ← 2D spacing
    "HowToCombineTransforms": ("Compose",),

    # Optimizer
    "MaximumNumberOfIterations": ("500", "1000", "2000"),
    "AutomaticParameterEstimation": ("false",),
    "SP_a": ("5524.8523145307626692", "17647.8036501390706690", "31086.7314993593172403"),
    "SP_A": ("20.0000000000000000", "20.0000000000000000", "20.0000000000000000"),
    "SP_alpha": ("1.0000000000000000", "1.0000000000000000", "1.0000000000000000"),
    "SigmoidMax": ("1.0000000000000000", "1.0000000000000000", "1.0000000000000000"),
    "SigmoidMin": ("-0.5721026323088569", "-0.6933698789512854", "-0.9270545620719912"),
    "SigmoidScale": ("0.0000054698958427", "0.0000010534700705", "0.0000002343077367"),
    "UseAdaptiveStepSizes": ("true",),

    # Metric
    "NumberOfHistogramBins": ("128",),

    # Several
    "DefaultOutputPrecision": ("16",),
    "WriteTransformParametersEachIteration": ("false",),
    "WriteTransformParametersEachResolution": ("true",),
    "WriteResultImageAfterEachResolution": ("false",),
    "WriteResultImage": ("false",),
    "ShowExactMetricValue": ("false",),
    "ErodeMask": ("false",),

    # ImageSampler
    "ImageSampler": ("RandomCoordinate",),
    "NumberOfSpatialSamples": ("942", "1884", "3768"),
    "NewSamplesEveryIteration": ("true",),

    # Interpolator and Resampler
    "BSplineInterpolationOrder": ("1",),
    "FinalBSplineInterpolationOrder": ("3",),
    "DefaultPixelValue": ("0",),
    }
     #  Only set FinalGridSpacingInVoxels (remove any reference to PhysicalUnits)
    #pamap_bspline['FinalGridSpacingInPhysicalUnits'] = ()

    #  Add essential parameters
    #pamap_bspline["Metric"] = ("AdvancedMattesMutualInformation",)
    #pamap_bspline["NumberOfResolutions"] = ("1",)
    
    # Add maps to registration parameters
    reg_params = itk.ParameterObject.New()
    reg_params.AddParameterMap(pamap_rigid)
    reg_params.AddParameterMap(pamap_bspline)
    
    # Run registration
    transformed_moving_image, result_transform_parameters = itk.elastix_registration_method(
            fixed_itk,
            moving_itk,
            parameter_object=reg_params,
            output_directory="Elastix/",
            log_to_file=True,
            log_to_console=False,
            number_of_threads=threads,
        )
    
    # Obtain deformation field
    
    ## Write input txt file
    points_x = np.arange(0, moving.shape[1], x_step)
    points_y = np.arange(0, moving.shape[0], y_step)

    with open("Elastix/points.txt", "w") as f:
        f.write("point\n")
        f.write(f"{len(points_x)*len(points_y)}\n")
        for x in points_x:
            for y in points_y:
                f.write(f"{x} {y}\n")
    
    ## Transformix
    ### Load Transformix Object
    transformix_object = itk.TransformixFilter.New(moving_itk)
    transformix_object.SetFixedPointSetFileName('Elastix/points.txt')
    transformix_object.SetTransformParameterObject(result_transform_parameters)

    # Set output directory for spatial jacobian and its determinant,
    # default directory is current directory.
    transformix_object.SetOutputDirectory('Elastix/')
    
    transformix_object.SetLogFileName('transformix.log')

    # Update object (required)
    transformix_object.UpdateLargestPossibleRegion()
    
    # Read deformation from outputpoints.txt
    deformation_field = np.zeros((math.ceil(moving.shape[0]/y_step), math.ceil(moving.shape[1]/x_step), 2))
    with open("Elastix/outputpoints.txt", "r") as f:
        lines = f.readlines()
        for line in lines:
            input_index = line.split(";")[1].split("=")[1].strip(" []\t")
            input_index = [int(i) for i in input_index.split()]
            input_index[0] = input_index[0]//x_step
            input_index[1] = input_index[1]//y_step
            
            deform = line.split(";")[5].split("=")[1].strip(" []\t")
            deform = [float(i) for i in deform.split()]
            
            deformation_field[input_index[1]][input_index[0]] = deform
            
    
    return deformation_field

def dft_displacement(img, ref, M=32, N=32, upsample_factor=100):
    """

    Args:
        img (numpy.ndarray): Moving image.
        ref (numpy.ndarray): Fixed/Reference image.
        M (int, optional): Half window size. Defaults to 32.
        N (int, optional): Grid size window size Defaults to 32.
        upsample_factor (int, optional): Upsample factor. Defaults to 100.

    Returns:
        deforms (numpy.ndarray): 2D array of displacment vectors. Index of vector correlates to
        postion at img. array([[[u,v],[...],...],[...],...])
        Shape is (int, int, 2).
        errors (numpy.ndarray): Array containing dft errors.

    """
    deforms = []
    errors = []
    pos = []
    for y in range(M,img.shape[0]-M, N):
        tmp = []
        tmp_coef = []
        tmp_pos = []
        for x in range(M, img.shape[1]-M, N):
            window = img[y-M:y+M, x-M:x+M]
            window = window.astype(np.float64)
            window_ref = ref[y-M:y+M, x-M:x+M]
            window_ref = window_ref.astype(np.float64)

            #Check for empty windows
            if window_ref.std() < 1e-3:
                tmp.append([np.nan, np.nan])
                tmp_coef.append(np.nan)
                tmp_pos.append([y,x])
                continue

            shift, error, dif = phase_cross_correlation(window_ref, window, upsample_factor=upsample_factor, normalization=None)
            tmp.append(shift)
            tmp_coef.append(error)
            tmp_pos.append([y, x])
        deforms.append(tmp)
        errors.append(tmp_coef)
        pos.append(tmp_pos)
        
    return np.array(deforms), np.array(errors), np.array(pos)

def  matlabNormcor(img, ref, M=32, N=32):
    """
    Docstring for matlabNormcor
    
    :param img: Moving image
    :param ref: Fixed image
    :param M: Half of patch size
    :param N: Grid size
    """
    results = []
    coeffs = []
    mean_coeffs = []
    
    # Loop over image
    for y in range(N, img.shape[0]-N,N):
        tmp_list = []
        tmp_list_coef = []
        tmp_list_mean_coef = []
        for x in range(N, img.shape[1]-N,N):
            ## Split image in windows
            window = img[y-M:y+M, x-M:x+M]
            
            ## Search window in arear of image window but bigger
            ref_window = ref[y-M:y+M, x-M:x+M]
            if ref_window.std() < 1e-3:
                tmp_list.append([np.nan, np.nan])
                tmp_list_coef.append(np.nan)
                tmp_list_mean_coef.append(np.nan)
                continue
            

            cor_map = normxcorr2(window, ref_window)
                       
            ## Compare correlation result with window postion
            pos_y, pos_x = np.where(cor_map==np.max(cor_map))
            if len(pos_x) == 0 or len(pos_y) == 0:
                pos_x = [cor_map.shape[1]/2, 0]
                pos_y = [cor_map.shape[0]/2, 0]
            pos_y = pos_y[0]
            pos_x = pos_x[0]
            
            ## Calculate displacement
            dif_x = cor_map.shape[1]/2 - pos_x
            dif_y = cor_map.shape[0]/2 - pos_y
            
            tmp_list.append([dif_y, dif_x])
            tmp_list_coef.append(np.max(cor_map))
            tmp_list_mean_coef.append(np.mean(np.abs(cor_map)))
        
        results.append(tmp_list)
        coeffs.append(tmp_list_coef)
        mean_coeffs.append(tmp_list_mean_coef)
    
    return np.array(results), np.array(coeffs), np.array(mean_coeffs)


def elastix_3d(before, after, parameter_file_path, x_step=12, y_step=12, surface=10):
    """Takes two z-stacks and computes deformation field.

    Args:
        before (nd.array): Z-stack before cell removal.
        after (nd.arrray): Z-stack after cell removal
        parameter_file_path (str): Path to parameter file.
        x_step (int): Grid spacing in x. Defaults to 12.
        y_step (int): Grid spacing in y. Defaults to 12.
        surface (int): Number of surface slice. Defaults to 10.

    Returns:
        ndarray: Deformationfield [y][x][uz,uy,ux]
    """
    ## Create folders
    if os.path.exists("Elastix"):
        shutil.rmtree("Elastix")
    os.makedirs("Elastix", exist_ok=True)
    fixed = itk.GetImageFromArray(after)
    moving = itk.GetImageFromArray(before)

    elastix = itk.ElastixRegistrationMethod.New(
        fixed,
        moving
    )

    elastix.SetParameterObject(
        itk.ParameterObject.New()
    )

    
    #parameter_path = pathlib.Path(__file__).parent.resolve()
    elastix.GetParameterObject().AddParameterFile(parameter_file_path)

    elastix.Update()

    result = elastix.GetOutput()

    transform_params = elastix.GetTransformParameterObject()


    ## Write input txt file
    points_x = np.arange(0, moving.shape[2], x_step)
    points_y = np.arange(0, moving.shape[1], y_step)

    with open("Elastix/points.txt", "w") as f:
        f.write("point\n")
        f.write(f"{len(points_x)*len(points_y)}\n")
        for x in points_x:
            for y in points_y:
                #for z in points_z:
                f.write(f"{x} {y} {surface}\n")

    transformix = itk.TransformixFilter.New(moving)
    transformix.SetTransformParameterObject(transform_params)
    transformix.SetFixedPointSetFileName("Elastix/points.txt")
    transformix.Update()

    # Read deformation from outputpoints.txt
    nx = math.ceil(moving.shape[2]/x_step)
    ny = math.ceil(moving.shape[1]/y_step)
    deformation_field = np.zeros((ny, nx, 3))
    with open("outputpoints.txt", "r") as f:
        lines = f.readlines()
        for line in lines:
            input_index = line.split(";")[1].split("=")[1].strip(" []\t")
            input_index = [int(i) for i in input_index.split()]
            dx = input_index[0]//x_step
            dy = input_index[1]//y_step
            
            deform = line.split(";")[5].split("=")[1].strip(" []\t")
            deform = [float(i) for i in deform.split()][::-1]
            if dx > nx or dy > ny :
                continue
            
            deformation_field[dy][dx] = deform
    
    return deformation_field

def RigidShift(before, after, u=100):
    """Calculates rigid shift caused by, for instance, stage movement.

    Args:
        before (nd.array): 2D array of image before cell removal.
        after (nd.array): 2D array of image after cell removal.
        u (int): Estimate for shift. Try to round up to next magnitude. Defaults to 100.

    Returns:
        tuple: Rigid shift uy, ux.
    """
    dis,_,_ = dft_displacement(before, after, u, u)
    ux = dis[:,:,0]
    uy = dis[:,:,1]
    return (np.mean(uy), np.mean(ux))

def rigid_shift_pcc(fixed, moving, upsample_factor=20):
    
    shift, error, _ = phase_cross_correlation(fixed, moving, upsample_factor=upsample_factor)
    # shift is (row_shift, col_shift) = (dy, dx)
    return float(shift[0]), float(shift[1])

def Surface(array):
    """Calculates the surface of a z-stack, assuming the surface
    has the highest intensity.

    Args:
        array (ndarray): z-stack of shape [z][y][x]

    Returns:
        int: index of slice with highest intensity.
    """
    l = [np.sum(z) for z in array]
    return l.index(max(l))