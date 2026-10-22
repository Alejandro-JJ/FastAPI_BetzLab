# Libraries
import matplotlib.pyplot as plt
import numpy as np

# Functions
def plot_dis_vec(vecs, cmap="jet", angles="xy", scale_units="xy", scale=None, mode="field", color="white"):
    """plots the results of cor_displacement as a vectorfield using matplotlib quiver and imshow.

    Args:
        vecs (numpy.ndarray): 2D array of displacement vectors.
        cmap (str, optional): colorstyle for vector magnitude. Defaults to "plasma".
        angles (str, optional): Method for determining the angle of the arrows. Defaults to "xy".
        scale_units (str, optional): unit of scales. Defaults to "xy".
        scale (float, optional): Scale of vectors. Defaults to None.
        mode (str, optional): What sort of plot to create. "field" is a vectorfield.
        "magnitude" is a colormap of vector magnitudes. "both" is a vectorfield on top
        of a colormap.
        color (str, optional): color of vectorfield on colormap.

    Returns:
        matplotlib.figure.Figure: plot of displacement field.
    """
    
    if mode not in ["field", "magnitude", "both"]:
        raise ValueError(
            f"mode has to be either 'field', 'magnitde' or 'both'. Got mode='{mode}'."
        )
    
    fig = plt.figure()
    ax = fig.add_axes([0,0,1,1]) 

    U = vecs[:,:,1]
    V = vecs[:,:,0]

    norm = np.sqrt(U**2+V**2)
    
    if mode=="field":
        qui = ax.quiver(U, V, norm, cmap=cmap, angles=angles, scale_units=scale_units, scale=scale)
        fig.colorbar(qui)
    elif mode=="magnitude":
        mag = ax.imshow(norm, cmap=cmap, origin='lower')
        fig.colorbar(mag)
    elif mode=="both":
        mag = ax.imshow(norm, cmap=cmap, origin='lower')
        fig.colorbar(mag)
        qui = ax.quiver(U, V, angles=angles, scale_units=scale_units, scale=scale, color=color)
    
    return fig