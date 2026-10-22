import numpy as np
from scipy import interpolate

def Bin2D(img, M, N):
    """
    Bins a 2D array with bin size MxN.
    img is puffed at the borders with zeros if bin size doesnt fit.

    Args:
        img (numpy.ndarray): 2D array.
        M (int): bin size in x.
        N (int): bin size in y.

    Returns:
        numpy.ndarray: binned 2D array.

    """
    if len(np.shape(img)) != 2:
        raise IndexError(
            f"Input array has to be 2D; got shape: {np.shape(img)}"
        )
    
    # Pad image at borders with zeros if nescessary.
    if img.shape[0]%N != 0:
        tmp_row = np.zeros((N-img.shape[0]%N ,img.shape[1]))
        img = np.vstack((img, tmp_row))
    
    if img.shape[1]%M != 0:
        tmp_col = np.zeros((img.shape[0], M-img.shape[1]%M))
        img = np.hstack((img, tmp_col))
    
    # Reshape to align bins on axis
    img = np.reshape(img,(img.shape[0]//N, N, img.shape[1]//M, M))
    
    return img.mean(-1).mean(1)

def interpolate2D(array):
    """
    Interpolates Nans inside 2D numpy arrays. Nans at borders are
    replaced with zero.
    
    Args:
        array (numpy.ndarray): 2D array.

    Returns:
        GD1 (numpy.ndarray): 2D array without Nans.

    """
    if np.isnan(np.sum(array))==False: return array
    else:
        x = np.arange(0, array.shape[1])
        y = np.arange(0, array.shape[0])
        #mask invalid values
        array = np.ma.masked_invalid(array)
        xx, yy = np.meshgrid(x, y)
        #get only the valid values
        x1 = xx[~array.mask]
        y1 = yy[~array.mask]
        newarr = array[~array.mask]

        GD1 = interpolate.griddata((x1, y1), newarr.ravel(),
                               (xx, yy),
                               method='cubic')
        GD1[np.isnan(GD1)]=0
        return GD1

def Filter_correlation(array,coeffs, mean_coeffs,cor_mean_thresh, thresh):
    """
    Removes vectors below a correlation threshold in an array containing
    displacement data obtained by cross correlation. Afterwards,
    displacements are interpolated.

    Args:
        array (numpy.ndarray): Displacement vectors.
        coeffs (numpy.ndarray): Correlation coefficients.
        thresh (float): Correlation threshold.

    Returns:
        numpy.ndarray: Filtered Displacements.

    """
    
    vecs = []
    copy = np.copy(array)
    copy[coeffs < thresh] = np.nan
    copy[coeffs < mean_coeffs*cor_mean_thresh] = np.nan
    for i in range(array.shape[-1]):
        vecs.append(interpolate2D(copy[:,:,i]))
    return np.stack(vecs, -1)

def Filter_dft(array, cor, thresh=0.85):
    """
    Removes vectors above an error threshold in an array containing
    displacement data obtained by dft. Afterwards,
    displacements are interpolated.

    Args:
        array (numpy.ndarray): Displacement vectors.
        cor (numpy.ndarray): Dft cor values.
        thresh (float): Error threshold.

    Returns:
        numpy.ndarray: Filtered Displacements.

    """
    vecs = []
    copy = np.copy(array)
    copy[cor < thresh] = np.nan
    for i in range(array.shape[-1]):
        vecs.append(interpolate2D(copy[:,:,i]))
    return np.stack(vecs, -1)
    
