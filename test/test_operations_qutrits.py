# This file is part of quantumsim. (https://gitlab.com/quantumsim/quantumsim)
# (c) 2018 Quantumsim Authors
# Distributed under the GNU GPLv3. See LICENSE.txt or
# https://www.gnu.org/licenses/gpl.txt

import numpy as np

from quantumsim import bases, PauliVector
import quantumsim.operations.qutrits as lib


class TestLibrary:
    def test_rotate_x(self):
        basis = (bases.general(3),)
        sys_bases = basis * 3
        dm = PauliVector(sys_bases)

        rotate90 = lib.rotate_x(0.5*np.pi)
        rotate180 = lib.rotate_x(np.pi)
        rotate360 = lib.rotate_x(2*np.pi)

        rotate90(dm, 1)
        rotate180(dm, 2)
        assert np.allclose(dm.meas_prob(0), (1, 0, 0))
        assert np.allclose(dm.meas_prob(1), (0.5, 0.5, 0))
        assert np.allclose(dm.meas_prob(2), (0, 1, 0))

        rotate180(dm, 1)
        assert np.allclose(dm.meas_prob(1), (0.5, 0.5, 0))

        rotate90(dm, 1)
        assert np.allclose(dm.meas_prob(1), (1, 0, 0))

        rotate360(dm, 0)
        assert np.allclose(dm.meas_prob(0), (1, 0, 0))

    def test_rotate_y(self):
        basis = (bases.general(3),)
        sys_bases = basis * 3
        dm = PauliVector(sys_bases)

        rotate90 = lib.rotate_y(0.5*np.pi)
        rotate180 = lib.rotate_y(np.pi)
        rotate360 = lib.rotate_y(2*np.pi)

        rotate90(dm, 1)
        rotate180(dm, 2)
        assert np.allclose(dm.meas_prob(0), (1, 0, 0))
        assert np.allclose(dm.meas_prob(1), (0.5, 0.5, 0))
        assert np.allclose(dm.meas_prob(2), (0, 1, 0))

        rotate180(dm, 1)
        assert np.allclose(dm.meas_prob(1), (0.5, 0.5, 0))

        rotate90(dm, 1)
        assert np.allclose(dm.meas_prob(1), (1, 0, 0))

        rotate360(dm, 0)
        assert np.allclose(dm.meas_prob(0), (1, 0, 0))

    def test_rotate_z(self):
        sqrt2 = np.sqrt(2)
        qubit_basis = (bases.general(3),)
        dm = PauliVector(qubit_basis)

        rotate90 = lib.rotate_z(0.5*np.pi)
        rotate180 = lib.rotate_z(np.pi)
        rotate360 = lib.rotate_z(2*np.pi)

        rotate90(dm, 0)
        assert np.allclose(dm.to_pv(), [1] + [0] * 8)
        rotate180(dm, 0)
        assert np.allclose(dm.to_pv(), [1] + [0] * 8)

        # manually apply a Hadamard gate
        had_expansion = np.array([0.5, 0.5, 0, sqrt2, 0, 0, 0, 0, 0])
        superpos_dm = PauliVector(qubit_basis, had_expansion)

        rotate180(superpos_dm, 0)
        assert np.allclose(superpos_dm.to_pv(),
                           [0.5, 0.5, 0, -sqrt2, 0, 0, 0, 0, 0])

        rotate90(superpos_dm, 0)
        assert np.allclose(superpos_dm.to_pv(),
                           [0.5, 0.5, 0, 0, -sqrt2, 0, 0, 0, 0])

        rotate180(superpos_dm, 0)
        assert np.allclose(superpos_dm.to_pv(),
                           [0.5, 0.5, 0, 0, sqrt2, 0, 0, 0, 0])

        rotate360(superpos_dm, 0)
        assert np.allclose(superpos_dm.to_pv(),
                           [0.5, 0.5, 0, 0, sqrt2, 0, 0, 0, 0])

    def test_hadamard(self):
        qubit_basis = (bases.general(3),)
        sys_bases = qubit_basis+qubit_basis
        dm = PauliVector(sys_bases)

        hadamard = lib.hadamard()

        hadamard(dm, 1)
        assert np.allclose(dm.meas_prob(0), (1, 0, 0))
        assert np.allclose(dm.meas_prob(1), (0.5, 0.5, 0))

        hadamard(dm, 1)
        assert np.allclose(dm.meas_prob(1), (1, 0, 0))

    def test_cphase_compatability(self):
        cz_op_nz = lib.cphase(angle=np.pi,
                              leakage_rate=0,
                              leakage_phase=-np.pi/2,
                              model='NetZero')

        cz_op_legacy = lib.cphase(angle=np.pi,
                                  leakage_rate=0,
                                  model='legacy')

        b = (cz_op_nz.bases_in, cz_op_nz.bases_out)
        assert np.allclose(cz_op_nz.ptm(*b), cz_op_legacy.ptm(*b))

        input_leakage_rate = 0.001
        cz_op_nz = lib.cphase(angle=np.pi,
                              leakage_rate=input_leakage_rate,
                              leakage_phase=-np.pi/2,
                              model='netzero')
        cz_op_legacy = lib.cphase(angle=np.pi,
                                  leakage_rate=4*input_leakage_rate,
                                  model='legacy')
        assert np.allclose(
            cz_op_nz.ptm(*b), cz_op_legacy.ptm(*b))
