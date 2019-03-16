"""Derivative of a Gaussian Contraction."""
import numpy as np
from scipy.special import comb, perm


# TODO: in the case of generalized Cartesian contraction where multiple shells have the same sets of
# exponents but different sets of primitive coefficients, it will be helpful to vectorize the
# `prim_coeffs` also.
def eval_deriv_contraction(coord, orders, center, angmom_comps, alphas, prim_coeffs):
    """Return the evaluation of the derivative of a Cartesian contraction.

    Parameters
    ----------
    coord : np.ndarray(3, N)
        Point in space where the derivative of the Gaussian primitive is evaluated.
    orders : np.ndarray(3,)
        Orders of the derivative.
        Negative orders are treated as zero orders.
    center : np.ndarray(3,)
        Center of the Gaussian primitive.
    angmom_comps : np.ndarray(L, 3)
        Component of the angular momentum that corresponds to this dimension.
    alphas : np.ndarray(K,)
        Values of the (square root of the) precisions of the primitives.
    prim_coeffs : np.ndarray(K,)
        Contraction coefficients of the primitives.

    Returns
    -------
    derivative : np.ndarray(L, N)
        Evaluation of the derivative.

    """
    # pylint: disable=R0914
    # support primitive evaluation
    if isinstance(alphas, (int, float)):
        alphas = np.array([alphas])
    if isinstance(prim_coeffs, (int, float)):
        prim_coeffs = np.array([prim_coeffs])
    # FIXME: I'm not a huge fan of this if statement. maybe the arrays should be ordered such that
    # the index for angular momentum vector goes last?
    if angmom_comps.ndim == 1:
        angmom_comps = angmom_comps[np.newaxis, :]

    # NOTE: following convention will be used to organize the axis of the multidimensional arrays
    # axis 0 = index for term in hermite polynomial (size: min(K, n)) where n is the order in given
    # dimension
    # axis 1 = index for primitive (size: K)
    # axis 2 = index for dimension (x, y, z) of coordinate (size: 3)
    # axis 3 = index for angular momentum vector (size: L)
    # axis 4 = index for coordinate (out of a grid) (size: N)
    # adjust the axis
    coord = coord[np.newaxis, np.newaxis, :, np.newaxis]
    # NOTE: if `coord` is two dimensional (3, N), then coord has shape (1, 1, 3, 1, N). If it is
    # one dimensional (3,), then coord has shape (1, 1, 3, 1)
    # NOTE: `order` is still assumed to be a one dimensional
    center = center[np.newaxis, np.newaxis, :, np.newaxis]
    angmom_comps = angmom_comps.T[np.newaxis, np.newaxis, :, :]
    # NOTE: if `angmom_comps` is two-dimensional (3, L), has shape (1, 1, 3, L). If it is one
    # dimensional (3, ) then it has shape (1, 1, 3)
    alphas = alphas[np.newaxis, :, np.newaxis, np.newaxis]
    # NOTE: `prim_coeffs` will be used as a 1D array

    # useful variables
    rel_coord = coord - center
    gauss = np.exp(-alphas * rel_coord ** 2)

    # zeroth order (i.e. no derivatization)
    indices_noderiv = orders <= 0
    zero_rel_coord, zero_angmom_comps, zero_gauss = (
        rel_coord[:, :, indices_noderiv],
        angmom_comps[:, :, indices_noderiv],
        gauss[:, :, indices_noderiv],
    )
    zeroth_part = np.prod(zero_rel_coord ** zero_angmom_comps * zero_gauss, axis=(0, 2))
    # NOTE: `zeroth_part` now has axis 0 for primitives, axis 1 for angular momentum vector, and
    # axis 2 for coordinate

    deriv_part = 1
    nonzero_rel_coord, nonzero_orders, nonzero_angmom_comps, nonzero_gauss = (
        rel_coord[:, :, ~indices_noderiv],
        orders[~indices_noderiv],
        angmom_comps[:, :, ~indices_noderiv],
        gauss[:, :, ~indices_noderiv],
    )
    nonzero_orders = nonzero_orders[np.newaxis, np.newaxis, :, np.newaxis]

    # derivatization part
    if nonzero_orders.size != 0:
        # General approach: compute the whole coefficents, zero out the irrelevant parts
        # NOTE: The following step assumes that there is only one set (nx, ny, nz) of derivatization
        # orders i.e. we assume that only one axis (axis 2) of `nonzero_orders` has a dimension
        # greater than 1
        indices_herm = np.arange(np.max(nonzero_orders) + 1)[:, np.newaxis, np.newaxis, np.newaxis]
        # get indices that are used as powers of the appropriate terms in the derivative
        # NOTE: the negative indices must be turned into zeros (even though they are turned into
        # zeros later anyways) because these terms are sometimes zeros (and negative power is
        # undefined).
        indices_angmom = nonzero_angmom_comps - nonzero_orders + indices_herm
        indices_angmom[indices_angmom < 0] = 0
        # get coefficients for all entries
        coeffs = (
            comb(nonzero_orders, indices_herm)
            * perm(nonzero_angmom_comps, nonzero_orders - indices_herm)
            * (-alphas ** 0.5) ** indices_herm
            * nonzero_rel_coord ** indices_angmom
        )
        # zero out the appropriate terms
        indices_zero = np.where(indices_herm < np.maximum(0, nonzero_orders - nonzero_angmom_comps))
        coeffs[indices_zero[0], :, indices_zero[2], indices_zero[3]] = 0
        indices_zero = np.where(nonzero_orders < indices_herm)
        coeffs[indices_zero[0], :, indices_zero[2]] = 0
        # compute
        # FIXME: I can't seem to vectorize the next part due to the API of
        # np.polynomial.hermite.hermval. The main problem is that the indices for the primitives and
        # the dimension must be constrained for the given `x` and `c`, otherwise the hermitian
        # polynomial is evaluated at many unnecessary points.
        hermite = np.prod(
            [
                [
                    [
                        np.polynomial.hermite.hermval(
                            alphas[:, i, 0, 0] ** 0.5 * nonzero_rel_coord[:, 0, j, 0],
                            coeffs[:, i, j, k],
                        )
                        for k in range(nonzero_angmom_comps.shape[3])
                    ]
                    for i in range(alphas.shape[1])
                ]
                for j in range(nonzero_rel_coord.shape[2])
            ],
            # NOTE: for loop over the axis 1 (primitives) and 2 (dimension) moves it to axis 1 and
            # 0, respectively, while removing these indices from alphas and coeffs. hermval returns
            # an array of c.shape[1:] + x.shape.
            # Therefore, axis 0 is for index for dimension (x, y, z)
            #            axis 1 is the index for primitive
            #            axis 2 is the index for angular momentum vector
            #            axis 3 is the index for term in hermite polynomial
            #            axis 4 is the index for coordinates
            axis=(0, 3),
        )
        # NOTE: `hermite` now has axis 0 for primitives and axis 1 for coordinates
        deriv_part = np.prod(nonzero_gauss, axis=(0, 2)) * hermite

    prim_coeffs = prim_coeffs[:, np.newaxis]
    return np.sum(prim_coeffs * zeroth_part * deriv_part, axis=0)


def eval_contraction(coord, center, angmom_comps, alphas, coeffs):
    """Return the evaluation of a Gaussian contraction.

    Parameters
    ----------
    coord : np.ndarray(3, N)
        Point in space where the derivative of the Gaussian primitive is evaluated.
    orders : np.ndarray(3,)
        Orders of the derivative.
        Negative orders are treated as zero orders.
    center : np.ndarray(3,)
        Center of the Gaussian primitive.
    angmom_comps : np.ndarray(3,)
        Component of the angular momentum that corresponds to this dimension.
    alphas : np.ndarray(K,)
        Values of the (square root of the) precisions of the primitives.
    prim_coeffs : np.ndarray(K,)
        Contraction coefficients of the primitives.

    Returns
    -------
    derivative : float
        Evaluation of the derivative.

    Returns
    -------
    contraction : float
        Evaluation of the contraction.

    """
    return eval_deriv_contraction(
        coord, np.zeros(center.shape), center, angmom_comps, alphas, coeffs
    )


# TODO: this function will likely be unused by anyone but is used for testing. Maybe it should be
# moved to the tests directory?
def eval_deriv_prim(coord, orders, center, angmom_comps, alpha):
    """Return the evaluation of the derivative of a Gaussian primitive.

    Parameters
    ----------
    coord : np.ndarray(3,)
        Point in space where the derivative of the Gaussian primitive is evaluated.
    orders : np.ndarray(3,)
        Orders of the derivative.
        Negative orders are treated as zero orders.
    center : np.ndarray(3,)
        Center of the Gaussian primitive.
    angmom_comps : np.ndarray(3,)
        Component of the angular momentum that corresponds to this dimension.
    alpha : float
        Value of the exponential in the Guassian primitive.

    Returns
    -------
    derivative : float
        Evaluation of the derivative.

    Note
    ----
    If you want to evaluate the derivative of the contractions of the primitive, then use
    `gbasis.deriv.eval_deriv_contraction` instead.

    """
    return eval_deriv_contraction(coord, orders, center, angmom_comps, alpha, 1)[0]


# TODO: this function will likely be unused by anyone but is used for testing. Maybe it should be
# moved to the tests directory?
def eval_prim(coord, center, angmom_comps, alpha):
    """Return the evaluation of a Gaussian primitive.

    Parameters
    ----------
    coord : np.ndarray(3,)
        Point in space where the derivative of the Gaussian primitive is evaluated.
    center : np.ndarray(3,)
        Center of the Gaussian primitive.
    angmom_comps : np.ndarray(3,)
        Component of the angular momentum that corresponds to this dimension.
    alpha : float
        Value of the exponential in the Guassian primitive.

    Returns
    -------
    derivative : float
        Evaluation of the derivative.

    Note
    ----
    If you want to evaluate the contractions of the primitive, then use
    `gbasis.deriv.eval_contraction` instead.

    """
    return eval_deriv_prim(coord, np.zeros(angmom_comps.shape), center, angmom_comps, alpha)