# Libraries
import numpy as np
import math
from scipy.optimize import newton,root,fsolve,root_scalar

def tensormulti(A,B):
    """Multiplies two tensors.

    Args:
        A (numpy.ndarray): Tensor A.
        B (numpy.ndarray): Tensor B.

    Returns:
        C (numpy.ndarray): Tensorproduct of A and B.

    """
    d1= np.shape(A)[0]
    d2= np.shape(B)[1]
    d= np.shape(A)[1]
    
    C = np.zeros((d1, d2, A[0,0].shape[0], A[0,0].shape[1]), dtype=B.dtype)
    
    for i in range(d1):
        for j in range(d2):
            #C[i,j] = A[i,0]*B[0,j] + A[i,1]*B[1,j] + A[i,2]*B[2,j]
            for k in range(d):
                C[i,j] += A[i,k]*B[k,j]
    #print(f"tensormulti:{A.shape} and {B.shape} goes to {C.shape}")
    return C


def tensorinverse(A):
    """Calculates inverse of a tensor.
    
    Args:
        A (numpy.ndarray): Tensor to be inverted.

    Returns:
        Ainv (numpy.ndarray): Inverted tensor.

    """
    d= np.shape(A)[0]
    Ainv=np.empty((d,d, A[0,0].shape[0], A[1,1].shape[1]), dtype=A.dtype)
    if d==2:
        det = A[0,0]*A[1,1] - A[0,1]*A[1,0]
        Ainv[0,0] = A[1,1]/det
        Ainv[0,1] = -A[0,1]/det
        Ainv[1,0] = -A[1,0]/det
        Ainv[1,1] = A[0,0]/det
    else:
        det = A[0,0]* (A[1,1]*A[2,2] - A[2,1]*A[1,2]) 
        - A[0,1]* (A[1,0]*A[2,2] - A[2,0]*A[1,2]) 
        + A[0,2]* (A[1,0]*A[2,1] - A[2,0]*A[1,1])
        Ainv[0,0] = 1/det*(A[1,1]*A[2,2] - A[1,2]*A[2,1])
        Ainv[0,1] = 1/det*(A[0,2]*A[2,1] - A[0,1]*A[2,2])
        Ainv[0,2] = 1/det*(A[0,1]*A[1,2] - A[0,2]*A[1,1]) 
        Ainv[1,0] = 1/det*(A[1,2]*A[2,0] - A[1,0]*A[2,2])
        Ainv[1,1] = 1/det*(A[0,0]*A[2,2] - A[0,2]*A[2,0])
        Ainv[1,2] = 1/det*(A[0,2]*A[1,0] - A[0,0]*A[1,2])
        Ainv[2,0] = 1/det*(A[1,0]*A[2,1] - A[1,1]*A[2,0])
        Ainv[2,1] = 1/det*(A[0,1]*A[2,0] - A[0,0]*A[2,1])
        Ainv[2,2] = 1/det*(A[0,0]*A[1,1] - A[0,1]*A[1,0])
    
    #print(f"tensorinverse: {A.shape} goes to {Ainv.shape}")
    
    return Ainv

def weightedtikhonovsolution(QctPbQ,QctPbFTu,alpha,d):
    """ Returns a regularized stress field for a given displacement field
    and regularization parameter.
    
    Args:
        QctPbQ (numpy.ndarray): Adjusted stress-displacement relation matrix.
        QctPbFTu (numpy.ndarray): Adjusted displacement matrix.
        alpha (float): Regularization parameter.
        d (int): Dimensions.

    Returns:
        FTf (numpy.ndarray): Regularized stress field.
        Ainv (numoy.ndarray: Inverted adjusted stress-displacement relation .

    """
    alpha=abs(alpha)
    A=np.copy(QctPbQ)
    for i in range(d):
        A[i,i] =QctPbQ[i,i]+ alpha
    Ainv=tensorinverse(A)
    
    FTf=tensormulti(Ainv,QctPbFTu)
    #print(f"tikhinov: {QctPbQ.shape} and {QctPbFTu.shape} goes to {FTf.shape} and {Ainv.shape}")
    
    return FTf, Ainv

def maxevidenceeq(fmp,alpha):
    """Expression that provides optimal regularization paramter at its root.
    
    Args:
        fmp (function): Function that returns regularized stress for a given
        regularization parameter.
        alpha (float): Regularization parameter.

    Returns:
        float: Function value. Needs to be zero for optimal regularization
        parameter.

    """
    alpha=abs(alpha)
    fm,Ainv=fmp(alpha)
    d=fm.shape[0]
    fmct= np.empty((d,1,fm[0,0].shape[0], fm[0,0].shape[1]), dtype=fm.dtype)
    for i in range(d):
        fmct[i,0] = np.conjugate(fm[i,0])
    fmsq1 = tensormulti(fmct,fm).real
    fmsq = np.square(np.abs(fm))
    #print(fmsq1-fmsq)
    trAinv=Ainv[0,0]
    for i in range(1,d):
        trAinv+=Ainv[i,i]

    out= d * np.prod(Ainv[0,0].shape) - alpha * np.sum(trAinv) - alpha * np.sum(fmsq)
    #print(f"maxevidence for {alpha} is {out}."
    return out

def perfft2(u):
    """Fourier transfrom using periodic plus smooth decomposition
    to avoid edge effects caused by DFT. Source is: 
    L. Moisan, "Periodic plus Smooth Image Decomposition", 
    Journal of Mathematical Imaging and Vision, vol 39:2, pp. 161-179, 2011.

    Args:
        u (numpy.ndarray): A 2D array to be fourier transformed

    Returns:
        numpy.ndarray: Fourier transformation of u.
    """

    s1,s2=np.shape(u)
    u=np.double(u)
    v1=np.zeros((s1,s2))
    v2=np.copy(v1)
    v1[0,:s2]=u[s1-1,:s2]-u[0,:s2]
    v1[0,:s2]=-v1[0,:s2]
    v2[:s1,0]=u[:s1,s2-1]-u[:s1,0]
    v2[:s1,s2-1]=-v2[:s1,0]
    
    v=v1+v2
    
    cos1 = np.tile(np.cos(2*np.pi * (np.arange(s1)[:, np.newaxis]) / s1), (1, s2))
    cos2 = np.tile(np.cos(2*np.pi * (np.arange(s2)[np.newaxis, :]) / s2), (s1, 1))
    
    den = 2 * (cos1 + cos2 - 2)
    den[0,0] = 1
    FTv = np.fft.fft2(v)
    FTv[0,0] = 0
    FTperu = np.fft.fft2(u) - FTv / den
    return FTperu


def tract(displacements,E,nu,mue2pix,alpha0,h,z,d, grid=[False,1], equillibrium=False):
    """Using an inverse solution (see "Imaging in-plane and normal stresses
    near an interface crack using traction force microscopy,
    Ye Xu, Eric R. Dufresne et al, PNAS Aug 2010") calculates the stresses to a
    given displacement field.
    
    Args:
        displacements (numpy.ndarray): Contains displacement vectors in micrometer.
        Must be 2D array where each element is d-dimensional vector.
        E (float): Young's modulus in Pa.
        nu (float): Poissons ratio.
        mue2pix (float): Pixel density.
        alpha0 (float): Initial value for regularization.
        h (float): Gel height.
        z (float): Depth.
        d (int): Dimensions.
        grid (list, optional): Wether displacements have been calculated
        grid based. First value is True if grid based and second is how many
        pixel the unit cell is wide. Defaults to [False,1].
        equillibrium (bool, optional): Wether equillibrium should be assumed
        or not. Defaults to False.

    Returns:
        dictionary: Tractions, Optimal Alpha,MaxEvidenceEquation, betaxy .

    """
    # Get vectors
    if d == 2:
        ux = displacements[:,:,1]
        uy = displacements[:,:,0]
    elif d == 3:
        ux = displacements[:,:,2]
        uy = displacements[:,:,1]
        uz = displacements[:,:,0]
    
    # Subtract median for better alignment
    ux -= np.median(ux)
    uy -= np.median(uy)
    if d == 3:
        uz -= np.median(uz)
    
    # Parameters
    #E = 9000 # Pa
    #nu = 0.49 # SI
    #mue2pix = 0.1083 # micrometer to pixel
    #alpha0 = 1e-10
    #h = 70  # micrometer
    #z = h
    #d = 2
    
    # Estimate beta
    sx = math.floor(ux.shape[1]/10)
    sy = math.floor(ux.shape[0]/10)
    N = np.prod(ux.shape)
    uxn = np.copy(ux)
    uyn = np.copy(uy)
    uxn[sy-1:-sy, sx-1:-sx] = np.nan
    uyn[sy-1:-sy, sx-1:-sx] = np.nan
    
    betaxy = 1/(N*(np.nanvar(uxn)+np.nanvar(uyn))/2)
    if d == 3:
        uzn = np.copy(uz)
        uzn[sy-1:-sy, sx-1:-sx] = np.nan
        betaz = 1/(N*np.nanvar(uzn))
    
    # Fourier using periodic plus smooth decomposition
    #Ftux = np.fft.fftshift(perfft2(ux))
    #Ftuy = np.fft.fftshift(perfft2(uy))
    Ftux = np.fft.fftshift(np.fft.fft2(ux))
    Ftuy = np.fft.fftshift(np.fft.fft2(uy))
    FTu = np.empty((d,1, Ftux.shape[0], Ftux.shape[1]), dtype=Ftux.dtype)
    FTu[0][0] = Ftux
    FTu[1][0] = Ftuy
    if d== 3:
        #Ftuz = np.fft.fftshift(perfft2(uz))
        Ftuz = np.fft.fftshift(np.fft.fft2(uz))
        FTu[2][0] = Ftuz
    # k matrix
    #create two matrices that correspond to the kx, and the ky coordinates
    #2*pi, normalizing by elements and shift needed because of analytical fourier expression
    #so in the end just from -pi to pi times amplitude factor given by pixel resolution
    #and in case of grid based calculation the distance between grid points
    #and distance between frequencies given by number of pixels
    #for even number of elements N fourier trafo puts zero frequency 
    #to N/2+1 so highest positive value is missing hence(N/2-1)/N*(2*pi/mue2pix)
    if grid[0]:
        dist = mue2pix*grid[1]
    else:
        dist = mue2pix    
    
    if ux.shape[1] % 2 > 0:
        kx = np.tile(np.linspace(-np.pi / dist, np.pi / dist, ux.shape[1]), (ux.shape[0], 1))
        zero1 = int(np.ceil(ux.shape[1] / 2))
    else:
        kx = np.tile(np.linspace(-np.pi / dist, (ux.shape[1] / 2 - 1) * 2 * np.pi / (ux.shape[1] * dist), ux.shape[1]), (ux.shape[0], 1))
        zero1 = int(ux.shape[1] / 2 + 1)

    if ux.shape[0] % 2 > 0:
        ky = np.tile(np.linspace(-np.pi / dist, np.pi / dist, ux.shape[0])[:, np.newaxis], (1, ux.shape[1]))
        zero0 = int(np.ceil(ux.shape[0] / 2))
    else:
        ky = np.tile(np.linspace(-np.pi / dist, (ux.shape[0] / 2 - 1) * 2 * np.pi / (ux.shape[0] * dist), ux.shape[0])[:, np.newaxis], (1, ux.shape[1]))
        zero0 = int(ux.shape[0] / 2 + 1)

    k = np.sqrt(kx**2 + ky**2)
    # To avoid zeros. This needs to be discussed
    k = np.where(k==0, 1e-100/dist, k)
    
    # analytically simplified version of the inverse of the in 
    # "Imaging in-plane and normal stresses near an interface crack using traction force microscopy,Ye Xu, Eric R. Dufresne et al, PNAS Aug 2010" 
    # presented matrix Q, which as opposed to the standard boussinesque solution corrects
    # for finite thickness and includes z directional forces
    
    ## Factors for hyperbolic sin and cosin
    sh=1-np.exp(-2*k*h)
    ch=1+np.exp(-2*k*h)
    sz=1-np.exp(-2*k*z)
    cz=1+np.exp(-2*k*z)
    pref = (1 + nu)/(ch*E*k**3*(ch**2*(4*(-1 + nu)**2 + k**2*h**2) - sh**2*((1 - 2*nu)**2 + k**2*h**2)))
    
    Qinv = np.empty((d,d,k.shape[0],k.shape[1]))
    if z==h:
        Qinv[0,0]=pref*(-2*cz*k**2*(-1 + nu)*( cz*(3 - 4*nu)*sz + cz**2*k*z - k*sz**2*z) + 2*ky**2*(cz**3*k*(-1 + nu)*z - cz*k*(-1 + nu)*sz**2*z + cz**2*sz*(1 - nu + k**2*z**2) - sz**3*(1 - 4*nu + 4*nu**2 + k**2*z**2)))
        Qinv[0,1]=pref*2*kx*ky*(-cz**3*k*(-1 + nu)*z + cz*k*(-1 + nu)*sz**2*z + cz**2*sz*(-1 + nu - k**2*z**2) + sz**3*(1 - 4*nu + 4*nu**2 + k**2*z**2))
        Qinv[1,0]=Qinv[0,1]
        Qinv[1,1]=pref*2*(ky**2*sz*(cz**2*(-1 + nu) + (1 - 2*nu)**2*sz**2) - k**2*sz*(-4*cz**2*(-1 + nu)**2 + (1 - 2*nu)**2*sz**2) - ky**2*cz*k*(-1 + nu)*(cz**2 - sz**2)*z + k**4*sz*(cz**2 - sz**2)*z**2 + ky**2*k**2*sz*(-cz**2 + sz**2)*z**2)
        if d==3:
            Qinv[0,2]=pref*1j*kx*cz*k*(cz**2*k**2*z**2 - sz**2*(3 - 10*nu + 8*nu**2 + k**2*z**2))
            #Qinv[1,2]=ky/kx*Qinv[0,2]; %can diverge this way
            Qinv[1,2]=pref*1j*ky*cz*k*(cz**2*k**2*z**2 - sz**2*(3 - 10*nu + 8.*nu**2 + k**2*z**2))
            Qinv[2,0]=-Qinv[0,2]
            Qinv[2,1]=-Qinv[1,2]
            Qinv[2,2]=pref*2*cz*k**2*(-1 + nu)*(cz*(-3 + 4*nu)*sz + cz**2*k*z - k*sz**2*z)
    else:
        prefzh=np.exp(k*(z - h))*pref
        Qinv[0,0]=prefzh*(ch*k**2*(-2*ch*cz*k*(-1 + nu)*z + k*(1 - 2*nu)*sh*sz*z - h*k*sh*((3 - 4*nu)*sz + cz*k*z) + ch*sz*(6 - 14*nu + 8*nu**2 + h*k**2*z)) + ky**2*(-2*(h**2*k**2 + (1 - 2*nu)**2)*sh**2*sz + ch**2*(sz*(2 - 2*nu + h*k**2*(2*h - z)) + 2*cz*k*(-1 + nu)*z) + ch*k*sh*(h*(3 - 4*nu)*sz + cz*h*k*z + (-1 + 2*nu)*sz*z)))
        Qinv[0,1]=prefzh*kx*ky*(2*(h**2*k**2 + (1 - 2*nu)**2)*sh**2*sz + ch*k*sh*(h*(-3 + 4*nu)*sz - cz*h*k*z + (1 - 2*nu)*sz*z) + ch**2*(-2*cz*k*(-1 + nu)*z + sz*(-2 + 2*nu + h*k**2*(-2*h + z))))
        Qinv[1,0]=Qinv[0,1]
        Qinv[1,1]=prefzh*(2*k**2*(ch**2*(h**2*k**2 + 4*(-1 + nu)**2) - (h**2*k**2 + (1 - 2*nu)**2)*sh**2)*sz + ky**2*(2*(h**2*k**2 + (1 - 2*nu)**2)*sh**2*sz + ch*k*sh*(h*(-3 + 4*nu)*sz - cz*h*k*z + (1 - 2*nu)*sz*z) + ch**2*(-2*cz*k*(-1 + nu)*z + sz*(-2 + 2*nu + h*k**2*(-2*h + z)))))

    
    ## Replace elements for zero frequency
    Qinv[0,0][zero0,zero1]=2*z*(1+nu)/E
    Qinv[0,1][zero0,zero1]=0
    Qinv[1,0][zero0,zero1]=0
    Qinv[1,1][zero0,zero1]=2*z*(1+nu)/E
    if d == 3:
        Qinv[0,2][zero0,zero1]=0
        Qinv[1,2][zero0,zero1]=0
        Qinv[2,0][zero0,zero1]=0
        Qinv[2,1][zero0,zero1]=0
        Qinv[2,2][zero0,zero1]=z*(1+nu)*(1-2*nu)/(E*(1-nu))
    

    #calculate matrices for tikhonov regularization with different weight for z component of data noise, that need to be
    #calculated only once
    Qt=np.transpose(Qinv, [1,0,2,3]) # I think matlabs transpose would work this way, not sure tho.
    
    #~~Legacy~~#
    #Qct= np.empty((d,d,Qt.shape[2],Qt.shape[3]))
    #for i in range(d):
    #    for j in range(d):
    #        Qct[i,j] = np.conjugate(Qt[i,j])
    Qct = np.conjugate(Qt)
    
    ## create precision (inverse covariant) matrix for noise (fourier space)
    n=ux.shape
    Pb=np.zeros((d,d,n[0],n[1]))
    Pb[0,0]=betaxy*np.ones(n)
    Pb[1,1]=Pb[0,0]
    if d == 3:
        Pb[2,2] = betaz*np.ones(n)
    
    QctPbQ=tensormulti(Qct,tensormulti(Pb,Qinv))
    QctPbFTu=tensormulti(Qct,tensormulti(Pb,FTu))
    
    # alpha dependent fourier space tikhonov solution for the force, which is
    # the mean of posterior or the most probable value (mp)
    FTfmp = lambda alpha: weightedtikhonovsolution(QctPbQ,QctPbFTu,alpha,d)
    
    # maximum evidence (marginal likelihood) equation for alpha
    evieq = lambda alpha: maxevidenceeq(FTfmp,alpha)
    #print("Are there nans in Qinv?",True in np.isnan(Qinv))
    
    # solve implicit equation for alpha starting at given alpha0
    #print(f"The maxevideq for matlab alpha {-2.25092064e-07} results in {evieq(-2.25092064e-07)}.")
    alphaOpt=fsolve(evieq,x0=alpha0)
    
    #print(f"The regularization parameter is: {alphaOpt}.")
    #print(f"The maxevideq results in {evieq(alphaOpt)}.")
    #print(f"betaxy is {betaxy}.")
    
    # give the tikhonov solution according to the optimal alpha
    #print("The optimal alpha is:",alphaOpt)
    FTfmpOpt, AinvOpt = FTfmp(alphaOpt)
    
    
    # If user wants to force an equilibrium, set zero frequency component of force field to
    # zero
    if equillibrium:
        for i in range(d):
            FTfmpOpt[i,0][zero0,zero1]=0
            
    # Back to real space
    fx=np.fft.ifft2(np.fft.ifftshift(FTfmpOpt[0,0]))
    fy=np.fft.ifft2(np.fft.ifftshift(FTfmpOpt[1,0]))
    if d>2:
        fz=np.fft.ifft2(np.fft.ifftshift(FTfmpOpt[2,0]))
        
    results = np.stack((fy,fx), -1)
    if d==3:
        results = np.stack((fz,fy,fx), -1)
    
    
    return {"tractions": results, "Optimal Alpha":alphaOpt,"MaxEvidenceEquation": evieq(alphaOpt), "betaxy":betaxy, "stiffness":E}
    
    