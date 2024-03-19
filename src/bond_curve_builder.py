
from pydantic.dataclasses import dataclass
from dataclasses import InitVar
from typing import ClassVar
import logging
import numpy as np
import statsmodels.api as sm

from common.model import NameDateClass
from common.chrono import Tenor
from lib import solver
from models.rate_curve import SpreadCurve, RateCurveNode
from models.bond import Bond
from rate_curve_builder import get_rate_curve

logger = logging.Logger(__name__)


@dataclass
class BondCurveModel(NameDateClass):

    _base_curve: str
    _bonds: list[Bond]
    
    @property
    def base_curve(self):
        return get_rate_curve(self._base_curve)

    @property
    def bonds(self):
        return self._bonds
    
    def build(self) -> True:
        """Builds bond curve"""


# Nelson Seigel method
@dataclass
class BondCurveNS(NameDateClass):
    
    _base_curve: str
    _coeffs: tuple[float, float, float]
    _decay_rate: float

    def get_rate(self, ins: Bond) -> float:
        dcf = ins.get_settle_dcf(ins.maturity_date)
        decay_rate = self._decay_rate
        decay_factor = np.exp(-self._decay_rate * dcf)
        slope_factor = (1 - decay_factor) / (decay_rate * dcf)
        return self._coeffs[0] + self._coeffs[1] * slope_factor + self._coeffs[2] * (slope_factor - decay_factor)

@dataclass
class BondCurveModelNS(BondCurveModel):
    _decay_rate: float = 1

    curve: ClassVar[BondCurveNS]

    def get_factor_params(self):
        xs = []
        decay_rate = self._decay_rate
        for ins in self.bonds:
            dcf = ins.get_settle_dcf(ins.maturity_date)
            decay_factor = np.exp(-decay_rate * dcf)
            slope_factor = (1 - decay_factor) / (decay_rate * dcf)
            xs.append([1, slope_factor, (slope_factor - decay_factor)])
        return xs
    
    def build(self):
        x_in = self.get_factor_params()
        crv = self.base_curve
        y = [b_obj.get_zspread(crv) for b_obj in self.bonds]
        # x_in = sm.add_constant(r_v[0], prepend=False)
        res = sm.OLS(y, x_in).fit()
        self.curve = BondCurveNS(self.date, self._base_curve, tuple(res.params), self._decay_rate)
        return True


# Non-parametric
@dataclass
class BondCurveModelNP(BondCurveModel):
    node_tenors: InitVar[list[str]] = ['1Y', '2Y', '5Y', '10Y', '30Y']

    spread_curve: ClassVar[SpreadCurve]

    def get_solver_error(self, values: list[float]) -> float:
        curve = self.spread_curve
        curve.update_nodes(log_values=values)
        err = 0
        for bnd in self.bonds:
            err += (bnd.get_price_from_curve(curve) - bnd.price) ** 2
        # n_dates = [self.date] + [nd.date for nd in curve.nodes]
        # r_values = [curve.get_forward_rate(n_dates[n_id], n_dates[n_id+1]) for n_id in range(len(values))]
        # for r_id in range(1, len(r_values)):
        #     err += (r_values[r_id] - r_values[r_id-1]) ** 2
        return err
    
    def _solver_error_prime(self, values: list[float]) -> list[float]:
        curve = self.spread_curve
        curve.update_nodes(log_values=values)
        error_primes = np.zeros(len(values), dtype=float)
        nodes = [RateCurveNode(self.date, 1)] + curve.nodes
        for bnd in self.bonds:
            price_error = bnd.get_price_from_curve(curve) - bnd.price
            price_prime = np.zeros(len(values), dtype=float)
            n_id = 0
            for cshf in bnd.cashflows:
                cshf_pv = cshf.amount * curve.get_df(cshf.date)
                if cshf.date > nodes[n_id+1].date:
                    n_id += 1
                date_ratio = (cshf.date - nodes[n_id].date) / (nodes[n_id+1].date - nodes[n_id].date)
                price_prime[n_id] += cshf_pv * date_ratio
                if n_id > 0:
                    price_prime[n_id-1] += cshf_pv * (1 - date_ratio)
            for n_i in range(n_id+1):
                error_primes[n_i] +=  2 * price_error * price_prime[n_i]
        return error_primes
    
    def build_solver(self) -> bool:
        init_guess = np.zeros(len(self.spread_curve.nodes), dtype=float)
        res = solver.find_fit(cost_f=self.get_solver_error,
                              init_guess=init_guess,
                              jacobian=self._solver_error_prime)
        self.spread_curve.update_nodes(log_values=res)
        return True
    
    def build(self):
        base_curve = self.base_curve
        base_date = base_curve.date
        nodes = [(Tenor(ndt).get_date(base_date), 1) for ndt in self.node_tenors]
        self.spread_curve = SpreadCurve(base_date, nodes, base_curve,
                                        interpolation_methods=[(None, 'LogLinear')],
                                        _daycount_type=base_curve._daycount_type,
                                        _calendar=base_curve._calendar)
        return self.build_solver()