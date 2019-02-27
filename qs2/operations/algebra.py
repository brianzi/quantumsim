import numpy as np
from functools import reduce, lru_cache
from itertools import chain


@lru_cache(maxsize=128)
def bases_kron(bases):
    return reduce(np.kron, [b.vectors for b in bases])


def single_kraus_to_ptm(kraus, basis_in, basis_out):
    return np.einsum("xab, zbc, ycd, zad -> xy",
                     basis_out.vectors, kraus, basis_in.vectors, kraus.conj(),
                     optimize=True).real


# def kraus_to_ptm(kraus, bases_in, bases_out):
#     shape = tuple(b.dim_pauli for b in chain(reversed(bases_out),
#                                              reversed(bases_in)))
#     # shape = tuple(b.dim_pauli for b in chain(bases_out, bases_in))
#     return np.einsum("xab, zbc, ycd, zad -> xy",
#                      bases_kron(bases_out), kraus,
#                      bases_kron(bases_in), kraus.conj(),
#                      optimize=True).real.reshape(shape)


def kraus_to_ptm(kraus, bases_in, bases_out):
    dim = bases_in[0].dim_hilbert
    nq = len(bases_in)
    if nq != len(bases_out):
        raise ValueError("Input and output bases must contain the same number"
                         " of elements")
    kraus = kraus.reshape([kraus.shape[0]] + [dim]*(2*nq))
    einsum_args = []
    for i, b in enumerate(bases_out):
        einsum_args.append(b.vectors)
        einsum_args.append([4*nq + i, 2*i, 2*i+1])
    einsum_args.append(kraus)
    einsum_args.append([6*nq] + [2*i + 1 for i in range(2*nq)])
    for i, b in enumerate(bases_in):
        einsum_args.append(b.vectors)
        einsum_args.append([5*nq + i, 2*(i+nq)+1, 2*(i+nq)])
    einsum_args.append(kraus.conj())
    einsum_args.append([6*nq] + [2*i for i in range(2*nq)])
    einsum_args.append([4*nq + i for i in range(2*nq)])
    return np.einsum(*einsum_args, optimize=True).real


def ptm_convert_basis(ptm, bi_old, bo_old, bi_new, bo_new):
    shape = tuple(b.dim_pauli for b in chain(reversed(bo_new),
                                             reversed(bi_new)))
    d_in = np.prod([b.dim_pauli for b in bi_old])
    d_out = np.prod([b.dim_pauli for b in bo_old])
    return np.einsum("xij, yji, yz, zkl, wlk -> xw",
                     bases_kron(bo_new), bases_kron(bo_old),
                     ptm.reshape((d_out, d_in)),
                     bases_kron(bi_old), bases_kron(bi_new),
                     optimize=True).real.reshape(shape)
