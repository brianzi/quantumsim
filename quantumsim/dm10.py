# This file is part of quantumsim. (https://github.com/brianzi/quantumsim)
# (c) 2016 Brian Tarasinski
# Distributed under the GNU GPLv3. See LICENSE.txt or
# https://www.gnu.org/licenses/gpl.txt

import numpy as np
import pycuda.driver as drv
import pycuda.gpuarray as ga

from . import ptm

import pycuda.autoinit

# load the kernels
from pycuda.compiler import SourceModule, DEFAULT_NVCC_FLAGS

import sys
import os

import warnings

package_path = os.path.dirname(os.path.realpath(__file__))

mod = None
for kernel_file in [
        sys.prefix +
        "/pycudakernels/primitives.cu",
        package_path +
        "/primitives.cu"]:
    try:
        with open(kernel_file, "r") as kernel_source_file:
            mod = SourceModule(
                kernel_source_file.read(), options=DEFAULT_NVCC_FLAGS+[
                    "--default-stream", "per-thread", "-lineinfo"])
            break
    except FileNotFoundError:
        pass

if mod is None:
    raise ImportError("could not find primitives.cu")

pycuda.autoinit.context.set_shared_config(
    drv.shared_config.EIGHT_BYTE_BANK_SIZE)

_two_qubit_ptm = mod.get_function("two_qubit_ptm")
_two_qubit_ptm.prepare("PPIII")
# _cphase = mod.get_function("cphase")
# _cphase.prepare("PIII")
_get_diag = mod.get_function("get_diag")
_get_diag.prepare("PPI")
_bit_to_pauli_basis = mod.get_function("bit_to_pauli_basis")
_bit_to_pauli_basis.prepare("PII")
_pauli_reshuffle = mod.get_function("pauli_reshuffle")
_pauli_reshuffle.prepare("PPII")
_single_qubit_ptm = mod.get_function("single_qubit_ptm")
_single_qubit_ptm.prepare("PPII")
_dm_reduce = mod.get_function("dm_reduce")
_dm_reduce.prepare("PIPII")
_trace = mod.get_function("trace")
_trace.prepare("Pi")
_swap = mod.get_function("swap")
_swap.prepare("PIII")
_two_qubit_general_ptm = mod.get_function("two_qubit_general_ptm")
_two_qubit_general_ptm.prepare("PPPIIIII")


class Density:

    _ptm_cache = {}

    def __init__(self, no_qubits, data=None):
        """Create a new density matrix for several qubits.

        Parameters
        ----------
        no_qubits: int
            Number of qubits.
        data: :class:`numpy.ndarray`, :class:`pycuda.gpuarray.array`,\
        :class:`pycuda.driver.DeviceAllocation` or `None`
            Must be of size (2**no_qubits, 2**no_qubits); is copied to GPU if
            not already there. Only upper triangle is relevant. If `data` is
            `None`, create a new density matrix with all qubits in ground
            state.
        """

        self.allocated_qubits = 0
        self.allocated_diag = -1

        self._set_no_qubits(no_qubits)

        self.diag_work = None

        if no_qubits > 15:
            raise ValueError(
                "no_qubits=%d is way too many qubits, are you sure?" %
                no_qubits)

        if isinstance(data, np.ndarray):
            if data.shape != (1 << no_qubits, 1 << no_qubits):
                raise ValueError(
                    "`data` shape is wrong (required {}; actual {})"
                    .format((1 << no_qubits, 1 << no_qubits), data.shape))
            data = data.astype(np.complex128)
            complex_dm = ga.to_gpu(data)
            block_size = 2**4
            grid_size = 2**max(no_qubits - 4, 0)
            grid = (grid_size, grid_size, 1)
            block = (block_size, block_size, 1)
            for i in range(self.no_qubits):
                _bit_to_pauli_basis.prepared_call(
                    grid, block, complex_dm.gpudata, 1 << i, self.no_qubits)

            self.data = ga.empty(self._size, np.float64)
            _pauli_reshuffle.prepared_call(
                grid,
                block,
                complex_dm.gpudata,
                self.data.gpudata,
                self.no_qubits,
                0)
        elif isinstance(data, ga.GPUArray):
            if data.size != self._size:
                raise ValueError(
                    "`data` size is wrong (required {}; actual {})"
                    .format(self._size, data.size))
            if data.dtype != np.float64:
                raise ValueError(
                    "`data` dtype is wrong (required {}; actual {})"
                    .format(np.float64, data.dtype))
            self.data = data
        elif data is None:
            d = np.zeros(self._size, np.float64)
            d[0] = 1
            self.data = ga.to_gpu(d)
        else:
            raise ValueError("type of data not understood")

    def _set_no_qubits(self, no_qubits):
        self.allocated_qubits = max(self.allocated_qubits, no_qubits)
        self.no_qubits = no_qubits

        self._size = 1 << (2 * no_qubits)
        self._blocksize = 2**8
        self._gridsize = 2**max(0, 2 * no_qubits - 8)

    def trace(self):

        if self.no_qubits > 10:
            raise NotImplementedError(
                "Trace not implemented for more than 10 qubits yet")
        if self.allocated_diag < self.no_qubits:
            self.diag_work = ga.empty((1 << self.no_qubits), dtype=np.float64)
            self.allocated_qubits = self.no_qubits
        block = (2**self.no_qubits, 1, 1)
        grid = (1, 1, 1)

        _get_diag.prepared_call(
            grid,
            block,
            self.data.gpudata,
            self.diag_work.gpudata,
            np.uint32(self.no_qubits))

        _trace.prepared_call(
            grid, block, self.diag_work.gpudata, -1, shared_size=8 * block[0])

        tr0 = self.diag_work[0].get()

        return tr0

    def renormalize(self):
        """Renormalize to trace one."""
        tr = self.trace()
        self.data *= np.float(1 / tr)

    def copy(self):
        "Return a deep copy of this Density."
        data_cp = self.data.copy()
        cp = Density(self.no_qubits, data=data_cp)
        return cp

    def to_array(self):
        "Return the entries of the density matrix as a dense numpy ndarray."
        complex_dm = ga.zeros(
            (1 << self.no_qubits, 1 << self.no_qubits), np.complex128)
        block_size = 2**4
        grid_size = 2**max(self.no_qubits - 4, 0)
        grid = (grid_size, grid_size, 1)
        block = (block_size, block_size, 1)
        _pauli_reshuffle.prepared_call(
            grid,
            block,
            complex_dm.gpudata,
            self.data.gpudata,
            self.no_qubits,
            1)
        for i in range(self.no_qubits):
            _bit_to_pauli_basis.prepared_call(
                grid, block, complex_dm.gpudata, 1 << i, self.no_qubits)

        return complex_dm.get()

    def get_diag(self):
        if self.allocated_diag < self.no_qubits:
            self.diag_work = ga.empty((1 << self.no_qubits), dtype=np.float64)
            self.allocated_qubits = self.no_qubits

        block = (2**8, 1, 1)
        grid = (2**max(0, self.no_qubits - 8), 1, 1)

        _get_diag.prepared_call(
            grid,
            block,
            self.data.gpudata,
            self.diag_work.gpudata,
            np.uint32(self.no_qubits))

        return self.diag_work.get()

    def cphase(self, bit0, bit1):
        warnings.warn(
            "cphase deprecated, use two_ptm instead",
            DeprecationWarning)

        cphase_ptm = ptm.double_kraus_to_ptm(np.diag([1, 1, 1, -1])).real

        self.apply_two_ptm(bit0, bit1, cphase_ptm)

        # _cphase.prepared_call(grid, block,
        # self.data.gpudata,
        # bit0, bit1,
        # self.no_qubits)

    def apply_two_ptm(self, bit0, bit1, ptm):
        self._validate_bit(bit0, 'bit0')
        self._validate_bit(bit1, 'bit1')

        key = hash(ptm.tobytes())
        try:
            ptm_gpu = self._ptm_cache[key]
        except KeyError:
            self._validate_ptm(ptm, (16, 16), 'ptm')
            self._ptm_cache[key] = ga.to_gpu(ptm)
            ptm_gpu = self._ptm_cache[key]

        block = (self._blocksize, 1, 1)
        grid = (self._gridsize, 1, 1)

        _two_qubit_ptm.prepared_call(grid,
                                     block,
                                     self.data.gpudata,
                                     ptm_gpu.gpudata,
                                     bit0,
                                     bit1,
                                     self.no_qubits,
                                     shared_size=8 * (256 + self._blocksize))

    def apply_ptm(self, bit, ptm):
        self._validate_bit(bit, 'bit')

        key = hash(ptm.tobytes())
        try:
            ptm_gpu = self._ptm_cache[key]
        except KeyError:
            self._validate_ptm(ptm, (4, 4), 'ptm')
            self._ptm_cache[key] = ga.to_gpu(ptm)
            ptm_gpu = self._ptm_cache[key]

        block = (self._blocksize, 1, 1)
        grid = (self._gridsize, 1, 1)

        _single_qubit_ptm.prepared_call(grid,
                                        block,
                                        self.data.gpudata,
                                        ptm_gpu.gpudata,
                                        bit,
                                        self.no_qubits,
                                        shared_size=8 * (17 + self._blocksize))

    def hadamard(self, bit):
        warnings.warn("hadamard deprecated, use apply_ptm",
                      DeprecationWarning)
        self.apply_ptm(bit, ptm.hadamard_ptm())

    def amp_ph_damping(self, bit, gamma, lamda):
        warnings.warn("amp_ph_damping deprecated, use apply_ptm",
                      DeprecationWarning)
        self.apply_ptm(bit, ptm.amp_ph_damping_ptm(gamma, lamda))

    def rotate_y(self, bit, angle):
        warnings.warn("rotate_y deprecated, use apply_ptm",
                      DeprecationWarning)
        self.apply_ptm(bit, ptm.rotate_y_ptm(angle))

    def rotate_x(self, bit, angle):
        warnings.warn("rotate_x deprecated, use apply_ptm",
                      DeprecationWarning)
        self.apply_ptm(bit, ptm.rotate_x_ptm(angle))

    def rotate_z(self, bit, angle):
        warnings.warn("rotate_z deprecated, use apply_ptm",
                      DeprecationWarning)
        self.apply_ptm(bit, ptm.rotate_z_ptm(angle))

    def add_ancilla(self, anc_st):
        """Add an ancilla in the ground or excited state as the highest new
        bit.
        """

        byte_size_of_smaller_dm = 2**(2 * self.no_qubits) * 8

        if self.allocated_qubits == self.no_qubits:
            # allocate larger memory
            new_dm = ga.zeros(self._size * 4, np.float64)
            offset = anc_st * 3 * byte_size_of_smaller_dm
            drv.memcpy_dtod(int(new_dm.gpudata) + offset,
                            self.data.gpudata, byte_size_of_smaller_dm)

            self.data = new_dm
        else:
            # reuse previously allocated memory
            if anc_st == 0:
                drv.memset_d8(int(self.data.gpudata) + byte_size_of_smaller_dm,
                              0, 3 * byte_size_of_smaller_dm)
            if anc_st == 1:
                drv.memcpy_dtod(
                    int(self.data.gpudata) + 3 * byte_size_of_smaller_dm,
                    self.data.gpudata, byte_size_of_smaller_dm)
                drv.memset_d8(self.data.gpudata, 0, 3 *
                              byte_size_of_smaller_dm)

        self._set_no_qubits(self.no_qubits + 1)

    def partial_trace(self, bit):
        self._validate_bit(bit, 'bit')
        if self.no_qubits > 10:
            raise NotImplementedError(
                "Trace not implemented for more than 10 qubits yet")
        if self.allocated_diag < self.no_qubits:
            self.diag_work = ga.empty((1 << self.no_qubits), dtype=np.float64)
            self.allocated_qubits = self.no_qubits
        block = (2**self.no_qubits, 1, 1)
        grid = (1, 1, 1)

        _get_diag.prepared_call(
            grid,
            block,
            self.data.gpudata,
            self.diag_work.gpudata,
            np.uint32(self.no_qubits))

        _trace.prepared_call(
            grid,
            block,
            self.diag_work.gpudata,
            bit,
            shared_size=8 *
            block[0])

        tr1, tr0 = self.diag_work[:2].get()
        return tr0, tr1

    def project_measurement(self, bit, state):
        self._validate_bit(bit, 'bit')

        block = (self._blocksize, 1, 1)
        grid = (self._gridsize, 1, 1)

        if bit != self.no_qubits - 1:
            _swap.prepared_call(grid, block,
                                self.data.gpudata,
                                bit,
                                self.no_qubits - 1,
                                self.no_qubits)

        if state == 1:
            byte_size_of_smaller_dm = 2**(2 * self.no_qubits - 2) * 8
            drv.memcpy_dtod(self.data.gpudata,
                            int(self.data.gpudata) + 3 *
                            byte_size_of_smaller_dm,
                            byte_size_of_smaller_dm)

        self._set_no_qubits(self.no_qubits - 1)

        return self

    def _validate_bit(self, number, name):
        if number < 0 or number >= self.no_qubits:
            raise ValueError(
                "`{name}` number {n} does not exist in the system, "
                "it contains {n_qubits} qubits in total."
                .format(name=name, n=number, n_qubits=self.no_qubits))

    def _validate_ptm(self, ptm, target_shape, name):
        if ptm.shape != target_shape:
            raise ValueError(
                "`{name}` shape must be {target_shape}, got {real_shape}"
                .format(name=name,
                        target_shape=target_shape,
                        real_shape=ptm.shape))
        if ptm.dtype != np.float64:
            raise ValueError(
                "`{name}` dtype must be {target_dtype}, got {real_dtype}"
                .format(name=name,
                        target_dtype=np.float64,
                        real_dtype=ptm.dtype))


class DensityGeneral(Density):
    """A subclass of Density that uses general_two_qubit_ptm as a backend,
    for testing purposes
    """

    def apply_two_ptm(self, bit0, bit1, ptm):
        self._validate_bit(bit0, 'bit0')
        self._validate_bit(bit1, 'bit1')

        # bit0 must be the smaller one.
        if bit1 < bit0:
            bit1, bit0 = bit0, bit1
            ptm = (np.einsum("abcd -> badc", ptm.reshape((4, 4, 4, 4)))
                   .reshape((16, 16)))

        key = hash(ptm.tobytes())
        try:
            ptm_gpu = self._ptm_cache[key]
        except KeyError:
            self._validate_ptm(ptm, (16, 16), 'ptm')
            self._ptm_cache[key] = ga.to_gpu(ptm)
            ptm_gpu = self._ptm_cache[key]

        # dim_a_out, dim_b_out, d_internal (arbitrary)
        block = (4, 4, 16)
        blocksize = 4*4*16
        gridsize = max(1, (4**self.no_qubits)//blocksize)
        grid = (gridsize, 1, 1)

        _two_qubit_general_ptm.prepared_call(grid,
                                             block,
                                             self.data.gpudata,
                                             self.data.gpudata,
                                             ptm_gpu.gpudata,
                                             4, 4,
                                             4**bit0,
                                             4**(bit1-bit0-1),
                                             4**self.no_qubits,
                                             shared_size=8 * (256 + blocksize))
