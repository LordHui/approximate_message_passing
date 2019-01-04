# coding=utf-8

import numpy  as np
from .utils import utils
import numba


class SelfAveragingLMMSEVAMPSolver(object):
    """ Naive self averaging vector approximate message passing solver (LMMSE form)
        in this version, singular value decomposition is executed at the constructor
    """

    def __init__(self, A, y, regularization_strength, dumping_coefficient):
        """constructor

        Args:
            A: observation matrix of shape (M, N)
            y: observed value of shape (M, )
            regularization_strength: regularization parameter
            dumping_coefficient: dumping coefficient
        """
        self.l = regularization_strength
        self.dumping = dumping_coefficient

        self.A = A.copy()
        self.y = y.copy()

        self.M, self.N = A.shape

        # SVD
        u, s, vh = np.linalg.svd(self.A)
        self.s = np.zeros(self.N)
        self.s[:len(s)] = s
        self.s2 = self.s * self.s
        self.U = u
        self.VT = vh
        self.V = self.VT.T
        self.S = np.zeros((self.M, self.N))
        self.S_inv = np.zeros((self.N, self.M))
        for i, val in enumerate(s):
            self.S[i, i] = s[i]
            self.S_inv[i, i] = 1.0 / s[i]

        self.y_tilde = self.S_inv @ self.U.T @ self.y

        self.d = np.random.normal(0.0, 1.0, self.N)

        # de-noising part
        self.x_hat_1 = np.random.normal(0.0, 1.0, self.N)
        self.alpha_1 = 1.0
        self.eta_1 = 1.0
        self.gamma_2 = 1.0
        self.r_2 = np.random.normal(0.0, 1.0, self.N)

        # Linear Minimum Mean Square Error (LMMSE) Estimator part
        self.x_hat_2 = np.random.normal(0.0, 1.0, self.N)
        self.alpha_2 = 1.0
        self.eta_2 = 1.0
        self.gamma_1 = 1.0
        self.r_1 = np.random.normal(0.0, 1.0, self.N)

    @numba.jit(parallel=True, nogil=True)
    def solve(self, max_iteration=50, tolerance=1e-5, message=False):
        """VAMP solver

        Args:
            max_iteration: maximum number of iterations to be used
            tolerance: stopping criterion
            message: convergence info

        Returns:
            estimated signal
        """
        convergence_flag = False
        abs_diff = 9999
        iteration_index = 9999

        for iteration_index in range(max_iteration):
            old_x_hat_1 = self.x_hat_1.copy()

            # denonising
            new_x_hat_1 = self.__update_x_hat_1()
            new_alpha_1 = self.__update_alpha_1()
            self.x_hat_1 = utils.update_dumping(old_x=self.x_hat_1, new_x=new_x_hat_1, dumping_coefficient=self.dumping)
            self.alpha_1 = new_alpha_1
            new_eta_1 = self.__update_eta_1()
            self.eta_1 = np.clip(
                utils.update_dumping(old_x=self.eta_1, new_x=new_eta_1, dumping_coefficient=self.dumping),
                a_min=1e-9,
                a_max=1e9)

            new_gamma_2 = self.__update_gamma_2()
            self.gamma_2 = np.clip(new_gamma_2, a_min=1e-9, a_max=1e9)
            new_r_2 = self.__update_r_2()
            self.r_2 = new_r_2

            # LMMSE estimation
            self.d = self.__update_d()
            new_x_hat_2 = self.__update_x_hat_2()
            new_alpha_2 = self.__update_alpha_2()
            self.x_hat_2 = new_x_hat_2
            self.alpha_2 = new_alpha_2
            new_eta_2 = self.__update_eta_2()
            self.eta_2 = new_eta_2

            new_gamma_1 = self.__update_gamma_1()
            self.gamma_1 = np.clip(new_gamma_1, a_min=1e-9, a_max=1e9)
            new_r_1 = self.__update_r_1()
            self.r_1 = new_r_1

            abs_diff = np.linalg.norm(old_x_hat_1 - self.x_hat_1) / np.sqrt(self.N)
            if abs_diff < tolerance:
                convergence_flag = True
                if message:
                    print("requirement satisfied")
                    print("abs_diff: ", abs_diff)
                    print("abs_estimate: ", np.linalg.norm(self.x_hat_1))
                    print("iteration number = ", iteration_index)
                    print()
                break
        if convergence_flag:
            pass
            # print("converged")
            # print("abs_diff=", abs_diff)
            # print("estimate norm=", np.linalg.norm(self.x_hat_1))
            # if np.linalg.norm(self.x_hat_1) != 0.0:
            #     print("relative diff= ", abs_diff / np.linalg.norm(self.x_hat_1))
            # print("iteration num=", iteration_index)
            # print()
        else:
            print("does not converged.")
            print("abs_diff=", abs_diff)
            print("estimate norm=", np.linalg.norm(self.x_hat_1))
            if np.linalg.norm(self.x_hat_1) != 0.0:
                print("relative diff= ", abs_diff / np.linalg.norm(self.x_hat_1))
            print("iteration num=", iteration_index + 1)
            print()

        return self.x_hat_1

    @numba.jit(parallel=True, nogil=True)
    def __update_x_hat_1(self):
        """ update x_hat_1

        Returns:
            new x_hat_1
        """
        v1 = (self.r_1 - self.l / self.gamma_1 * np.sign(self.r_1))
        v2 = np.heaviside(np.abs(self.r_1) - self.l / self.gamma_1, 0.5)
        return v1 * v2

    @numba.jit(parallel=True, nogil=True)
    def __update_alpha_1(self):
        """update alpha_1

        Returns:
            new alpha_1
        """
        v1 = np.heaviside(np.abs(self.r_1) - self.l / self.gamma_1, 0.5)
        return np.mean(v1)

    @numba.jit(parallel=True, nogil=True)
    def __update_eta_1(self):
        """update eta_1

        Returns:
            new eta_1
        """
        return self.gamma_1 / self.alpha_1

    @numba.jit(parallel=True, nogil=True)
    def __update_gamma_2(self):
        """update gamma_2

        Returns:
            new gamma_2
        """
        return self.eta_1 - self.gamma_1

    @numba.jit(parallel=True, nogil=True)
    def __update_r_2(self):
        """update r_2

        Returns:
            new r_2
        """
        return (self.eta_1 * self.x_hat_1 - self.gamma_1 * self.r_1) / self.gamma_2

    @numba.jit(parallel=True, nogil=True)
    def __update_x_hat_2(self):
        """update x_hat_2

        Returns:
            new x_hat_2
        """

        def __calc_v1(r2):
            return r2

        def __calc_v2(V, d, y_tilde):
            return V @ (d * y_tilde)

        def __calc_v3(V, d, VT, r2):
            v1 = VT @ r2
            v2 = d * v1
            return V @ v2

        v1 = __calc_v1(self.r_2)
        v2 = __calc_v2(self.V, self.d, self.y_tilde)
        v3 = __calc_v3(self.V, self.d, self.VT, self.r_2)
        return v1 + v2 - v3

    @numba.jit(parallel=True, nogil=True)
    def __update_alpha_2(self):
        """update alpha_2

        Returns:
            new alpha_2
        """
        return 1.0 - self.d.mean()

    @numba.jit(parallel=True, nogil=True)
    def __update_eta_2(self):
        """update eta_2

        Returns:
            new eta_2
        """
        return self.gamma_2 / self.alpha_2

    @numba.jit(parallel=True, nogil=True)
    def __update_gamma_1(self):
        """update gamma_1

        Returns:
            new gamma_1
        """
        return self.eta_2 - self.gamma_2

    @numba.jit(parallel=True, nogil=True)
    def __update_r_1(self):
        """update r_1

        Returns:
            new r_1
        """
        return (self.eta_2 * self.x_hat_2 - self.gamma_2 * self.r_2) / self.gamma_1

    @numba.jit(parallel=True, nogil=True)
    def __update_d(self):
        """get d

        Returns:
            new d
        """
        return self.s2 / (self.s2 + self.gamma_2)

    def show_me(self):
        """debug method"""
        pass