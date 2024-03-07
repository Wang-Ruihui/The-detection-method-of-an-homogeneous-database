# -*- coding: utf-8 -*-
"""
Automatic detection of solar active regions from synoptic magnetograms

"""

import numpy as np
import cv2
import scipy
from astropy.io import fits
from skimage import measure, morphology
from ARparameters import ARArea, ARFlux, ARLocat, ARBmax, IDF, FDF, FDFBMR

# ------------------------------------------------------------------------------


def imshow(ax, data):
    """
    show image in 3 cigma way
    """
    mean = np.average(data)
    std = np.std(data)
    Y, X = data.shape
    vmin = mean-3*std
    vmax = mean+3*std
    if vmax > np.max(data):
        vmax = np.max(data)
    if vmin < np.min(data):
        vmin = np.min(data)

    ax.imshow(data, cmap='gray', vmin=vmin, vmax=vmax,
              origin='lower')  # cmap='gray'


def adaptiveThreshold(img_input, size, const):
    """
    adaptive threshold segmentation

    """
    img_smt = cv2.GaussianBlur(img_input, (size, size), 0, borderType=2)
    img_threshold = img_smt + const
    img_result = img_input - img_threshold

    img_result[np.where(img_result > 0)] = 1
    img_result[np.where(img_result < 0)] = 0

    return img_result


def threshold(img_input):
    """
    intensity threshold segmentation
    """

    img_input1 = np.abs(img_input).astype("int16")

    # img_input 'int16'
    img_thresh = adaptiveThreshold(img_input1, 501, 10)

    return img_thresh

# ------------------------------------------------------------------------------


class Point(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def getX(self):
        return self.x

    def getY(self):
        return self.y


def selectConnects(p):
    # connection types,p=0: 4 connection; p=1：8 connection;
    if p != 0:
        connects = [Point(-1, -1), Point(0, -1), Point(1, -1), Point(1, 0),
                    Point(1, 1), Point(0, 1), Point(-1, 1), Point(-1, 0)]
    else:
        connects = [Point(0, -1), Point(1, 0), Point(0, 1), Point(-1, 0)]
    return connects


def findseeds(img, origion_img, thresh):
    # find seeds used in region growing. Each seed should be stronger than 50G
    seedlist = []
    # the coordinates of remain pixels in array
    index = np.where(img == 1)
    # the values of remain pixels in array
    value = origion_img[img == 1]

    # get the coordinates of pixels stronger than 50G
    seedindex = np.where(abs(value) > 50)[0]
    for i in range(len(seedindex)):
        index1 = seedindex[i]
        point = Point(index[0][index1], index[1][index1])
        seedlist.append(point)

    return seedlist


def regionGrow(img, seeds, thresh, p=1):
    row, col = img.shape
    # image after region growing
    seedMark = np.zeros(img.shape, 'uint8')
    seedList = seeds[:]
    label = 1
    connects = selectConnects(p)
    while (len(seedList) > 0):
        currentPoint = seedList.pop(0)

        seedMark[currentPoint.x, currentPoint.y] = label
        if p == 1:
            n = 8
        else:
            n = 4

        for i in range(n):
            # the coordinates of neighbour pixels
            tmpX = currentPoint.x + connects[i].x
            tmpY = currentPoint.y + connects[i].y

            # if the neignbour pixel is beyond the image, skip it
            if tmpX < 0 or tmpY < 0 or tmpX >= row or tmpY >= col:
                continue
            # if the neignbour pixel is not labelled, judge its value
            elif seedMark[tmpX, tmpY] == 0:
                Bval = abs(img[tmpX, tmpY])
                if Bval > thresh:
                    seedMark[tmpX, tmpY] = label
                    seedList.append(Point(tmpX, tmpY))
    return seedMark

# ------------------------------------------------------------------------------


def RemoveUnipolar(img_input, img_label):
    # remove unipolar regions
    # relabel the remain ARs
    flag = 1
    for i in range(1, np.max(img_label) + 1):
        AR = img_input[np.where(img_label == i)]
        pos = AR[np.where(AR > 0)]
        neg = AR[np.where(AR < 0)]
        # totoal flux
        FluxSign = np.sum(pos) + np.sum(neg)
        # total ungisn flux
        FluxNoSign = np.sum(pos) + np.abs(np.sum(neg))

        if abs(FluxSign) >= 0.5 * FluxNoSign:
            img_label[np.where(img_label == i)] = 0
        else:
            img_label[np.where(img_label == i)] = flag
            flag = flag + 1

    return img_label


def RemoveRepeatAR(img_a, img_b, img4_b, rt):
    """
    remove repeat AR 
    img_a, image from the last CR
    img_b, original image needing processing
    img4_b, the Binary image of img_b after module4
    rt: threshold of flux ratio of the repeat ARs
    """
    # size of image, m, n
    m, n = np.shape(img4_b)
    # create a same img as img4_b
    img_copy = np.copy(img4_b)
    # img_b ater module 4 with true flux
    img_b = img_b*img4_b
    # label of img_b
    label_b = measure.label(img4_b)

    # differential rotation, (degree); 13.2 is the velocity of CR rotation
    omga = 13.562 - 13.20
    omgb = -2.040
    omgc = -1.487

    # duration of one CR
    dt = 27.27

    # sin latitude
    s = np.linspace(-3**0.5/2, 3**0.5/2, m)
    # differential roration velocity
    omg = omga + omgb*s**2 + omgc*s**4
    # pixels of derotation degree
    deg = -omg*dt*10
    dmax = np.max(deg)
    dmin = np.min(deg)

    # a big image to contain all pixels of the original image after differential rotation
    n1 = n + int(dmax - dmin)
    img_b1 = np.zeros((m, n1))
    label_b1 = np.zeros((m, n1))

    # img_b and label_b after derotate the differential rotation
    for i in range(1248):
        # index of pixels start and end
        index_s = int(deg[i] - dmin)
        index_e = n + int(deg[i] - dmin)
        img_b1[i, index_s:index_e] = img_b[i, :]
        label_b1[i, index_s:index_e] = label_b[i, :]

    # reshape to the original image size
    img_b2 = img_b1[:, int(-dmin):int(n - dmin)]
    label_b2 = label_b1[:, int(-dmin):int(n - dmin)]

    # get the unsigned flux ratios of ARs with same location
    # a,ratio;b,polarity
    a = np.zeros(np.max(label_b))
    b = np.zeros(np.max(label_b))
    for i in range(np.max(label_b)):
        # label starts from 1 and i starts from 0
        index = (label_b2 == i+1)
        # remove ARs disappearing after deratation
        if np.max(index*1) == 1:
            new = img_b2*index
            old = img_a*index
            fnus = np.sum(abs(new))
            fn = np.sum(new)
            fous = np.sum(abs(old))
            fo = np.sum(old)
            # due to data missing, sometimes fo==0;drop them
            if fous > 0:
                a[i] = fous/fnus
                b[i] = np.sign(fo/fn)*abs(fn/fnus)*abs(fo/fous)

    # remove ARs with ratio bigger than ratio threshold rt and with same polarity
    label_arr = np.where((a > rt)*(b > -0.5))[0] + 1
    for i in range(len(label_arr)):
        lab = label_arr[i]
        index = (label_b == lab)
        img_copy[index] = 0

    return img_copy

# ------------------------------------------------------------------------------


def ARdetection(img_old, rt, img_input, Kernel1, Kernel2, Thresh, Kernel3, Size, Kernel4):
    """
    img_old  : image of the last CR
    rt       : threshold of flux ratio of the repeat ARs
    img_input: input FITS file
    Kernel1  : closing operation kernel in module2
    Kernel2  : opening operation kernel in module2
    Thresh   : region grow threshold
    Kernel3  : closing operation kernel in module4
    Size     : the smallest size of AR,any region smaller than it will be removed.
    Kernel4  : dilating operation kernel in module5

    return:  result after each module,detection result, 
            boundary and labels of all ARs
    """
    # module1: intensity threshold segmentation, adaptive threshold
    module1 = threshold(img_input)

    # module2: morphological closing operation and opening operation to
    #          remove small magnetic segments and get the kernel pixels of ARs
    module2 = cv2.morphologyEx(module1, cv2.MORPH_CLOSE, Kernel1)
    module2 = cv2.morphologyEx(module2, cv2.MORPH_OPEN, Kernel2)

    # module3: region growing
    seeds = findseeds(module2, img_input, Thresh)
    module3 = regionGrow(img_input, seeds, Thresh)

    # module4: closing operation and remove small decayed ARs segments
    module4 = cv2.morphologyEx(module3, cv2.MORPH_CLOSE, Kernel3)
    module4 = morphology.remove_small_objects(module4.astype('bool'), Size)
    module4 = module4.astype("uint8")

    # module42: removing the repeat ARs
    module42 = RemoveRepeatAR(img_old, img_input, module4, rt)

    # module5: merging neighbor regions and removing unipolar regions
    # merge neighbor regions
    module42 = module42.astype("uint8")
    img_shape = cv2.dilate(module42, Kernel4)
    img_label = measure.label(img_shape)
    img_label = img_label * module42

    # remove unipolar regions
    img_label = RemoveUnipolar(img_input, img_label)
    module5 = np.where(img_label >= 1, 1, 0)

    # get the border of each merged AR
    img_shape1 = np.where(img_label >= 1, 1, 0).astype('uint8')
    img_shape2 = cv2.dilate(img_shape1, Kernel4)
    img_border = img_shape2 - cv2.erode(img_shape2, np.ones((3, 3)))

    # final detection result
    result = module5 * img_input

    return module1, module2, module3, module4, module42, module5, result, \
        img_label, img_border


# -------------------------------------------------------------------------------
'''
functions to detect ARs using the above detection modules
'''


def Get_ARi(File, Filetype, File_old, rt):
    """
    # get AR detection image of File after each module

    file : fits file of map
    filetype: MDI or HMI
    file_old: map of the last CR
    """
    input_file = fits.open(File)
    img_input = input_file[0].data
    input_file.close()

    input_file2 = fits.open(File_old)
    img_old = input_file2[0].data
    input_file2.close()

    # limit the latitude to (-60,60) or (-pi/3,pi/3) to remove polar magnetic field
    rowN = img_input.shape[0]
    PR = int((1 - np.sin(np.pi/3))*rowN/2)
    img_input = img_input[PR:rowN-PR, :]
    img_old = img_old[PR:rowN-PR, :]

    # remove the nan value
    img_input[np.isnan(img_input)] = 0
    img_old[np.isnan(img_old)] = 0

    # set control parameters
    # closing operation kernel in module2
    Kernel1 = np.ones((3, 3))  # CLOSE kernel

    if Filetype == 'MDI':
        # opening operation kernel in module2
        Kernel2 = np.ones((11, 11))
        # region gorwing threshold
        Thresh = 50

    elif Filetype == 'HMI':
        Kernel2 = np.ones((9, 9))  # OPEN kernel
        Thresh = 30  # region gorwing threshold

    # closing operation kernel in module4
    Kernel3 = np.ones((5, 5))  # Opening and closing kernel
    # ARs area threshold in module4
    Size = 351
    # dilating operation kernel in module5
    Kernel4 = np.ones((23, 23))

    module1, module2, module3, module4, module42, module5, result, img_label, img_border\
        = ARdetection(img_old, rt, img_input, Kernel1, Kernel2, Thresh, Kernel3, Size, Kernel4)

    return img_input, module1, module2, module3, module4, module42, module5, \
        result, img_label, img_border


def Get_ARP(File, Filetype, File_old, lamr, rt):
    """
    get AR parameters from synoptic magnetograms

    file : fits file of map
    filetype: MDI or HMI
    file_old: map of the last CR

    Returns：param (17*num)(num: AR number in this CR)

           param[0,:]: Carrington rotation
           param[2:4,:]: position of the AR positive polarity
           param[4:6,:]: position of the AR negative polarity
           param[6:8,:]: position of the whole AR
           param[8:10,:]: area of the AR positive polarity and negative polarity
           param[10,:]: flux of the AR positive polarity
           param[11,:]: flux of the AR negative polarity   
           param[12,:]: max unsigned magnetic field of AR             
           param[13, :] = idf
           param[14, :] = fdf    
           param[15, :] = idf with BMR approximation
           param[16, :] = fdf with BMR approximation
           for all position, the first row is latitude and the second is longitude
           parameters in each column is for an same AR
    """
    input_file = fits.open(File)
    CR = input_file[0].header['CAR_ROT']
    input_file.close()

    # extraction ARs from magnet0gram
    result = Get_ARi(File, Filetype, File_old, rt)

    # segment picture,result[4] is the module5,the result of Closing operation
    img_input = result[0]
    img_label = result[8]
    num = np.max(img_label)

    CR_array = np.ones(num)*CR
    area = ARArea(img_label, img_input)
    flux = ARFlux(img_label, img_input)
    location = ARLocat(img_label, img_input)
    # the max unsigned magnetic field of AR
    Bmax = ARBmax(img_label, img_input)

    idf = IDF(img_label, img_input)
    fdf = FDF(img_label, img_input, lamr)
    # the BMR approximation of idf and fdf
    idfbmr, fdfbmr = FDFBMR(flux, location, lamr)

    param = np.zeros((17, num))
    param[0, :] = CR_array
    param[1, :] = np.linspace(1, num, num)
    param[2:8, :] = location
    param[8:10, :] = area
    param[10:12, :] = flux
    param[12, :] = Bmax
    param[13, :] = idf
    param[14, :] = fdf
    param[15, :] = idfbmr
    param[16, :] = fdfbmr

    return param
