import cv2 # imports OpenCV
import numpy as np
from matplotlib import pyplot as plt #imports matplotlib
from scipy.ndimage import gaussian_filter

# image_enhancement_pipeline.py
def pltImg(img, title=None, ori="horizontal", colorb=True):
    im = plt.imshow(img, cmap='gray' if img.ndim == 2 else None)
    if colorb:
        plt.colorbar(im, orientation=ori, fraction=0.046, pad=0.04)
    if title:
        plt.title(title)
    plt.axis('off')

def load_rgb_image(path):
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Image not found: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def invert_and_gray(img_rgb):
    inverted = cv2.bitwise_not(img_rgb)
    gray = cv2.cvtColor(inverted, cv2.COLOR_BGR2GRAY)
    return inverted, gray

def compute_local_std(img_gray, psize):
    img = img_gray.astype(np.float64)
    x, y = img.shape
    score_temp = np.zeros((x, y, len(psize)))
    for i, size in enumerate(psize):
        local_mean = cv2.boxFilter(img, -1, (size, size))
        local_var = cv2.boxFilter(img**2, -1, (size, size)) - local_mean**2
        score_temp[:, :, i] = np.sqrt(np.clip(local_var, a_min=0, a_max=None)) 
    return score_temp

def compute_cci(score_temp, tolerance):
    x, y, _ = score_temp.shape
    tol = 1 - (tolerance / 100)
    tolerance_array = [(tol ** (6 - i)) for i in range(7)]
    tolerance_matrix = np.tile(tolerance_array, (x, y, 1))
    mult = score_temp * tolerance_matrix
    CCI = np.argmin(mult, axis=2) + 1
    return CCI

def compute_dark_channel(inverted, CCI):
    x, y, _ = inverted.shape
    dark_channel = np.zeros_like(inverted, dtype=np.float64)
    prange_biggest = 7
    extended = np.pad(inverted, ((prange_biggest, prange_biggest), (prange_biggest, prange_biggest), (0, 0)), mode='symmetric')
    for i in range(x):
        for j in range(y):
            cpx, cpy = i + prange_biggest, j + prange_biggest
            prange = round(8 - CCI[i, j])
            patch = extended[cpx - prange:cpx + prange, cpy - prange:cpy + prange, :]
            dark_channel[i, j, 0] = np.min(patch[:, :, 0])
            dark_channel[i, j, 1] = np.min(patch[:, :, 1])
            dark_channel[i, j, 2] = np.min(patch[:, :, 2])
    return dark_channel

def contrast_guided_atm_light(dc_channel, CCI, multiplier):
    h, w = dc_channel.shape
    result = np.zeros((h, w))
    prange_biggest = 7
    ext = np.pad(dc_channel, prange_biggest * multiplier, mode='symmetric')
    upsilon = [3 * multiplier - (multiplier / 3) * i for i in range(7)]
    upsilon = np.floor_divide(upsilon, 2)
    for i in range(h):
        for j in range(w):
            cpx, cpy = i + prange_biggest * multiplier, j + prange_biggest * multiplier
            c = int(CCI[i, j])
            prange = int(upsilon[7 - c])
            patch = ext[cpx - prange:cpx + prange, cpy - prange:cpy + prange]
            result[i, j] = np.max(patch)
    return result

def estimate_transmission(img_inv, atm_light_filt, CCI, w=0.9):
    x, y, _ = img_inv.shape
    normalized = img_inv.astype(np.float32) / (atm_light_filt + 1e-8)
    normalized[np.isnan(normalized)] = 0
    transmm = np.zeros((x, y))
    prange_biggest = 7
    padded = np.pad(normalized, ((prange_biggest, prange_biggest), (prange_biggest, prange_biggest), (0, 0)), mode='symmetric')
    for i in range(x):
        for j in range(y):
            cpx, cpy = i + prange_biggest, j + prange_biggest
            prange = int(8 - CCI[i, j])
            patch = padded[cpx - prange:cpx + prange, cpy - prange:cpy + prange, :]
            transmm[i, j] = 1 - (w * np.min(patch))
    return transmm

def recover_radiance(img_inv, atm_light_filt, transmm, t0=0.02):
    x, y, _ = img_inv.shape
    img = img_inv.astype('float32') / 255.0
    atm = atm_light_filt / 255.0
    J = np.zeros_like(img)
    for i in range(3):
        diff = img[:, :, i] - atm[:, :, i]
        tmax = np.maximum(transmm, t0)
        J[:, :, i] = diff / tmax + atm[:, :, i]
    return 1 - J

def run_full_pipeline(img):
    inverted, gray = invert_and_gray(img)
    score = compute_local_std(gray, [15, 13, 11, 9, 7, 5, 3])
    CCI = compute_cci(score, tolerance=3)
    dark = compute_dark_channel(inverted, CCI)
    atm5 = np.stack([contrast_guided_atm_light(dark[:, :, c], CCI, 5) for c in range(3)], axis=-1)
    atm5 = gaussian_filter(atm5, sigma=10)
    trans5 = estimate_transmission(inverted, atm5, CCI)
    output5 = recover_radiance(inverted, atm5, trans5)
    return output5