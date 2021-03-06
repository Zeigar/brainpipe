"""Connectivity correction function."""
import numpy as np
import pandas as pd

def _axes_correction(axis, ndim, num):
    """Get a slice at a specific axis."""
    axes = [slice(None)] * ndim
    axes[axis] = num
    return tuple(axes)


def get_pairs(n, part='upper', as_array=True):
    """Get connectivity pairs of the upper triangle.

    Parameters
    ----------
    n : int
        Number of electrodes.
    part : {'upper', 'lower', 'both'}
        Part of the connectivity array to get.
    as_array : bool | True
        Specifify if returned pairs should be a (n_pairs, 2) array or a tuple
        of indices.

    Returns
    -------
    pairs : array_like
        A (n_pairs, 2) array of integers.
    """
    assert part in ['upper', 'lower', 'both']
    if part == 'upper':
        idx = np.triu_indices(n, k=1)
    elif part == 'lower':
        idx = np.tril_indices(n, k=-1)
    elif part == 'both':
        high = np.c_[np.triu_indices(n, k=1)]
        low = np.c_[np.tril_indices(n, k=-1)]
        _idx = np.r_[high, low]
        idx = (_idx[:, 0], _idx[:, 1])
    if as_array:
        return np.c_[idx]
    else:
        return idx


def remove_site_contact(mat, channels, mode='soft', remove_lower=False,
                        symmetrical=False):
    """Remove proximate contacts for SEEG electrodes in a connectivity array.

    Parameters
    ----------
    mat : array_like
        A (n_elec, n_elec) array of connectivity.
    channels : list
        List of channel names of length n_elec.
    mode : {'soft', 'hard'}
        Use 'soft' to only remove successive contacts and 'hard' to remove all
        connectivty that come from the same electrode.
    remove_lower : bool | False
        Remove lower triangle.
    symmetrical : bool | False
        Get a symmetrical mask.

    Returns
    -------
    select : array_like
        Array of boolean values with True values in the array that need to be
        removed.
    """
    from re import findall
    n_elec = len(channels)
    assert (mat.shape == (n_elec, n_elec)) and mode in ['soft', 'hard']
    # Define the boolean array to return :
    select = np.zeros_like(mat, dtype=bool)
    # Find site letter and num :
    r = [[findall(r'\D+', k)[0]] + findall(r'\d+', k) for k in channels]
    r = np.asarray(r)
    for i, k in enumerate(r):
        letter, digit_1, digit_2 = [k[0], int(k[1]), int(k[2])]
        if mode is 'soft':
            next_contact = [letter, str(digit_1 + 1), str(digit_2 + 1)]
            to_remove = np.all(r == next_contact, axis=1)
        else:
            to_remove = r[:, 0] == letter
            to_remove[i] = False
        select[i, to_remove] = True
    # Remove lower triangle :
    select[np.tril_indices(n_elec)] = remove_lower
    # Symmetrical render :
    if symmetrical:
        select = symmetrize(select.astype(int)).astype(bool)
    select[np.diag_indices(n_elec)] = True
    return select


def anat_based_reorder(c, df, col, part='upper'):
    """Reorder and connectivity array according to anatomy.

    Parameters
    ----------
    c : array_like
        Array of (N, N) connectivity.
    df : pd.DataFrame
        DataFrame containing anamical informations.
    col : str
        Name of the column to use in the DataFrame.
    part : {'upper', 'lower', 'both'}
        Part of the connectivity array to get.

    Returns
    -------
    c_r : array_like
        Anat based reorganized connectivity array.
    labels : array_like
        Array of reorganized labels.
    index : array_like
        Array of indices used for the reorganization.
    """
    assert isinstance(c, np.ndarray) and c.ndim == 2
    assert col in df.keys()
    n_elec = c.shape[0]
    # Group DataFrame column :
    grp = df.groupby(col).groups
    labels = list(df.keys())
    index = np.concatenate([list(k) for k in grp.values()])
    # Get pairs :
    pairs = np.c_[get_pairs(n_elec, part=part, as_array=False)]
    # Reconstruct the array :
    c_r = np.zeros_like(c)
    for k, i in pairs:
        row, col = min(index[k], index[i]), max(index[k], index[i])
        c_r[row, col] = c[k, i]
    return c_r, labels, index


def anat_based_mean(x, df, col, fill_with=0., xyz=None):
    """Get mean of a connectivity array according to anatomical structures.

    Parameters
    ----------
    x : array_like
        Array of (N, N) connectivity.
    df : pd.DataFrame
        DataFrame containing anamical informations.
    col : str
        Name of the column to use in the DataFrame.
    fill_with : float | 0.
        Fill non-connectivity values.
    xyz : array_like | None
        Array of coordinate of each electrode.

    Returns
    -------
    x_r : array_like
        Mean array of connectivity inside structures.
    labels : array_like
        Array of labels used to take the mean.
    xyz_r : array_like
        Array of mean coordinates. Return only if `xyz` is not None.
    """
    assert isinstance(x, np.ndarray) and x.ndim == 2
    assert col in df.keys()
    # Get labels and roi's indices :
    gp = df.groupby(col, sort=False).groups
    labels, rois = list(gp.keys()), list(gp.values())
    n_roi = len(labels)

    # Process the connectivity array :
    np.fill_diagonal(x, 0.)
    is_masked = np.ma.is_masked(x)
    if is_masked:
        x.mask = np.triu(x.mask)
        np.fill_diagonal(x.mask, True)
        x += x.T
        con = np.ma.ones((n_roi, n_roi), dtype=float)
    else:
        x = np.triu(x)
        x += x.T
        con = np.zeros((n_roi, n_roi), dtype=float)

    # Take the mean inside rois :
    for r, rows in enumerate(rois):
        _r = np.array(rows).reshape(-1, 1)
        for c, cols in enumerate(rois):
            con[r, c] = x[_r, np.array(cols)].mean()

    # xyz coordinates :
    if xyz is None:
        return con, list(labels)
    elif isinstance(xyz, np.ndarray) and len(df) == xyz.shape[0]:
        df['X'], df['Y'], df['Z'] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        df = df.groupby(col, sort=False).mean().reset_index().set_index(col)
        df = df.loc[labels].reset_index()
        return con, list(labels), np.array(df[['X', 'Y', 'Z']])


def ravel_connect(connect, part='upper'):
    """Ravel a connectivity array.

    Parameters
    ----------
    connect : array_like
        Connectivity array of shape (n_sites, n_sites) to ravel
    part : {'upper', 'lower', 'both'}
        Part of the connectivity array to get.

    Returns
    -------
    connect : array_like
        Ravel version of the connectivity array.
    """
    assert isinstance(connect, np.ndarray) and (connect.ndim == 2)
    assert connect.shape[0] == connect.shape[1]
    pairs = get_pairs(connect.shape[0], part=part, as_array=False)
    return connect[pairs]


def unravel_connect(connect, n_sites, part='upper'):
    """Unravel a connectivity array.

    Parameters
    ----------
    connect : array_like
        Connectivity array of shape (n_sites, n_sites) to ravel
    n_sites : int
        Number of sites in the connectivity array.
    part : {'upper', 'lower', 'both'}
        Part of the connectivity array to get.

    Returns
    -------
    connect : array_like
        Unravel version of the connectivity array.
    """
    assert isinstance(connect, np.ndarray) and (connect.ndim == 1)
    pairs = get_pairs(n_sites, part=part, as_array=False)
    connect_ur = np.zeros((n_sites, n_sites), dtype=connect.dtype)
    connect_ur[pairs[0], pairs[1]] = connect
    return connect_ur


def symmetrize(arr):
    """Make an array symmetrical.

    Parameters
    ----------
    arr : array_like
        Connectivity array of shape (n_sources, n_sources)

    Returns
    -------
    arr : array_like
        Symmetrical connectivity array.
    """
    assert isinstance(arr, np.ndarray)
    assert (arr.ndim == 2) and (arr.shape[0] == arr.shape[1])
    return arr + arr.T - np.diag(arr.diagonal())


def concat_connect(connect, fill_with=0.):
    """Concatenate connectivity arrays.

    Parameters
    ----------
    connect : list, tuple
        List of connectivity arrays.
    fill_with : float | 0.
        Fill value.

    Returns
    -------
    aconnect : array_like
        Merged connectivity arrays.
    """
    assert isinstance(connect, (list, tuple)), ("`connect` should either be a "
                                                "list or a tuple of arrays")
    assert np.all([k.ndim == 2 for k in connect]), ("`connect` sould be a list"
                                                    " of 2d arrays")
    # Shape inspection :
    shapes = [k.shape[0] for k in connect]
    sh = np.sum([shapes])
    aconnect = np.full((sh, sh), fill_with, dtype=float)
    # Inspect if any masked array :
    if np.any([np.ma.is_masked(k) for k in connect]):
        aconnect = np.ma.masked_array(aconnect, mask=True)
    # Merge arrays :
    q = 0
    for k, (c, s) in enumerate(zip(connect, shapes)):
        sl = slice(q, q + s)
        aconnect[sl, sl] = c
        q += s
    return aconnect
