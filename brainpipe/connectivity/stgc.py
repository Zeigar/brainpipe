"""Single-trials covariance-based Granger Causality for gaussian variables.

-------------------- Total Granger interdependence ----------------------
Total Granger interdependence:
TGI = GC(x,y)
TGI = sum(GC,2):
TGI = GC(x->y) + GC(y->x) + GC(x.y)
TGI = GC(x->y) + GC(y->x) + GC(x.y) = Hycy + Hxcx - Hxxcyy
This quantity can be defined as the Increment of Total
Interdependence and it can be calculated from the different of two
mutual informations as follows

----- Relations between Mutual Information and conditional entropies ----
I(X_i+1,X_i|Y_i+1,Y_i) = H(X_i+1) + H(Y_i+1) - H(X_i+1,Y_i+1)
Ixxyy   = log(det_xi1) + log(det_yi1) - log(det_xyi1)
I(X_i|Y_i) = H(X_i) + H(Y_i) - H(X_i, Y_i)
Ixy     = log(det_xi) + log(det_yi) - log(det_yxi)
ITI(np) = Ixxyy - Ixy

Reference
Brovelli A, Chicharro D, Badier JM, Wang H, Jirsa V (2015)

Copyright of Andrea Brovelli (Jan 2015)

------------------------------ Python adaptation ------------------------------
Author: Etienne Combrisson <e.combrisson@gmail.com>

* Matlab `cov` and `np.cov` are slightly different (floating points). Those
  small floating point differences are then propagated using log.
* Matlab `log` support <0 numbers (and return complex) but not `np.log`. To fix
  it, with use `numpy.lib.scimath.log`. Could also use `np.log(x + 0j)`
"""
import logging

import numpy as np
from numpy.linalg import det
from numpy.lib.scimath import log

from ..system import set_log_level, progress_bar

logger = logging.getLogger('brainpipe')


def covgc_time(x, dt, lag, t0, verbose=None):
    """Single trials covariance-based Granger Causality for gaussian variables.

    Parameters
    ----------
    x : array_like
        Data array of shape (n_sources, n_time_samples)
    dt : int
        Duration of the time window for covariance correlation in samples
    lag : int
        Number of samples for the lag within each trial
    t0 : int
        Zero time in samples

    Returns
    -------
    gc : array_like
        Granger Causality arranged as (number of pairs) x (3 directionalities
        (pair[:, 0]->pair[:, 1], pair[:, 1]->pair[:, 0], instantaneous))
    pairs : array_like
        Indices of sources arranged as number of pairs x 2

    Notes
    -----
    Brovelli, A., Lachaux, J.-P., Kahane, P., and Boussaoud, D. (2005).
    High gamma frequency oscillatory activity dissociates attention from
    intention in the human premotor cortex. NeuroImage 28, 154–164.
    doi:10.1016/j.neuroimage.2005.05.045.
    """
    set_log_level(verbose)
    assert all([isinstance(k, int) for k in [dt, lag, t0]])
    logger.info("Compute single trial Granger Causality. Parameters :"
                "\n    Time window : %i samples\n    Lag : %i samples"
                "\n    Zero-time : %i samples" % (dt, lag, t0))
    # Data parameters. Size = sources x time points
    n_so, n_ti = x.shape
    # Select a single window according to index t0
    ind_t_single = np.arange(t0 - dt, t0)
    # Create indeces for all lags (broadcasting)
    ind_t = ind_t_single.reshape(1, -1) - np.arange(lag + 1).reshape(-1, 1)
    ind_t = ind_t.ravel()
    # Pairs between sources
    pairs = np.c_[np.triu_indices(n_so, k=1)]
    n_pairs = pairs.shape[0]
    # Init
    gc = np.zeros((n_pairs, 3), dtype=complex)
    # Normalisation coefficient for gaussian entropy
    # c = np.log( 2 * np.pi * np.exp(1))  # not use
    # Loop over number of pairs
    for i_p, p in enumerate(pairs):
        progress_bar(i_p, n_pairs, pre_st='    Computing pair ')
        # Extract data for a given pair of sources
        x_ = np.squeeze(x[p[0], ind_t]).reshape(lag + 1, dt)
        y_ = np.squeeze(x[p[1], ind_t]).reshape(lag + 1, dt)

        # ---------------------------------------------------------------------
        # Conditional Entropies
        # ---------------------------------------------------------------------
        # h_ycy : H(Y_i+1|Y_i) = H(Y_i+1) - H(Y_i)
        det_yi1 = det(np.cov(y_))
        det_yi = det(np.cov(y_[1::, :]))
        h_ycy = log(det_yi1) - log(det_yi)
        # h_ycx : H(Y_i+1|X_i,Y_i) = H(Y_i+1,X_i,Y_i) - H(X_i,Y_i)
        det_yxi1 = det(np.cov(np.r_[y_, x_[1::, :]]))
        det_yxi = det(np.cov(np.r_[y_[1::, :], x_[1::, :]]))
        h_ycx = log(det_yxi1) - log(det_yxi)
        # h_xcx : H(X_i+1|X_i) = H(X_i+1) - H(X_i)
        det_xi1 = det(np.cov(x_))
        det_xi = det(np.cov(x_[1::, :]))
        h_xcx = log(det_xi1) - log(det_xi)
        # h_xcy : H(X_i+1|X_i,Y_i) = H(X_i+1,X_i,Y_i) - H(X_i,Y_i)
        det_xyi1 = det(np.cov(np.r_[x_, y_[1::, :]]))
        h_xcy = log(det_xyi1) - log(det_yxi)
        # h_xxcyy: H(X_i+1,Y_i+1|X_i,Y_i) = H(X_i+1,Y_i+1,X_i,Y_i) - H(X_i,Y_i)
        det_xyi1 = det(np.cov(np.r_[x_, y_]))
        h_xxcyy = log(det_xyi1) - log(det_yxi)

        # ---------------------------------------------------------------------
        # Causality measures
        # ---------------------------------------------------------------------
        gc[i_p, 0] = h_ycy - h_ycx            # gc[pairs[:, 0] -> pairs[:, 1]]
        gc[i_p, 1] = h_xcx - h_xcy            # gc[pairs[:, 1] -> pairs[:, 0]]
        gc[i_p, 2] = h_ycx + h_xcy - h_xxcyy  # gc[x_.y_]

    gc_real = np.abs(gc)
    gc_real[np.isinf(gc_real)] = 0.
    gc_real[np.isnan(gc_real)] = 0.

    return gc_real, pairs