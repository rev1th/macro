from pydantic.dataclasses import dataclass
from dataclasses import field
import numpy as np
import statsmodels.api as sm
import pandas as pd
import datetime as dtm

from common.base_class import NameDateClass
from common.chrono.tenor import Tenor
from common.chrono.daycount import DayCount
from common.numeric import solver
from instruments.rate_curve import SpreadCurve, RateCurveNode, RollForwardCurve
from instruments.bonds.bond import Bond, BondYieldParameters
from models.curve_context import CurveContext


@dataclass
class BondCurveModel(NameDateClass):

    _base_curve: str
    _bonds: list[tuple[Bond, float]]
    
    def base_curve(self):
        return CurveContext().get_rate_curve(self._base_curve, self.date)
    
    def build(self) -> True:
        """Builds bond curve"""
    
    def get_graph_info(self):
        bond_measures = []
        curve = CurveContext().get_rate_curve(self._base_curve, self.date)
        yield_method = BondYieldParameters()
        for bnd, _ in self._bonds:
            date = bnd.maturity_date
            bond_measures.append([
                date,
                self.spread_curve.get_spread_rate(date, yield_method._compounding),
                bnd.get_zspread(self.date, curve),
                bnd.display_name(),
            ])
        bond_df = pd.DataFrame(bond_measures, columns=['Maturity', 'Asset Spread', 'ZSpread', 'Name'])
        bond_df.set_index('Maturity', inplace=True)
        bond_df.sort_index(inplace=True)
        prefix = f"{self.name}:{dtm.datetime.strftime(self.date, '%d-%b')}:"
        return {prefix: bond_df}, None


# Nelson Seigel method
@dataclass
class BondCurveNS(NameDateClass):
    
    _base_curve: str
    _daycount: DayCount
    _coeffs: tuple[float, float, float]
    _decay_rate: float

    def get_spread_rate(self, date: dtm.date, *args) -> float:
        dcf = self._daycount.get_dcf(self.date, date)
        decay_rate = self._decay_rate
        decay_factor = np.exp(-self._decay_rate * dcf)
        slope_factor = (1 - decay_factor) / (decay_rate * dcf)
        return self._coeffs[0] + self._coeffs[1] * slope_factor + self._coeffs[2] * (slope_factor - decay_factor)

@dataclass
class BondCurveModelNS(BondCurveModel):
    _decay_rate: float = 1
    _daycount: DayCount = DayCount.ACT365

    spread_curve: BondCurveNS = field(init=False)

    def get_factor_params(self):
        xs = []
        decay_rate = self._decay_rate
        for ins, _ in self._bonds:
            dcf = self._daycount.get_dcf(ins.settle_date, ins.maturity_date)
            decay_factor = np.exp(-decay_rate * dcf)
            slope_factor = (1 - decay_factor) / (decay_rate * dcf)
            xs.append([1, slope_factor, (slope_factor - decay_factor)])
        return xs
    
    def build(self):
        x_in = self.get_factor_params()
        crv = self.base_curve()
        y = [bond.get_zspread(self.date, crv) for bond, _ in self._bonds]
        # x_in = sm.add_constant(r_v[0], prepend=False)
        res = sm.OLS(y, x_in).fit()
        self.spread_curve = BondCurveNS(self.date, self._base_curve, self._daycount, tuple(res.params), self._decay_rate)
        return True


# Non-parametric
@dataclass
class BondCurveModelNP(BondCurveModel):
    _node_tenors: list[str] | None

    spread_curve: SpreadCurve = field(init=False)

    def __post_init__(self):
        wsum = sum(wi for _, wi in self._bonds)
        self.bonds_weight = [(bond, wi/wsum) for bond, wi in self._bonds if wi > 0]
        if self._node_tenors:
            self.nodes = [(Tenor(ndt).get_date(self.date), 1) for ndt in self._node_tenors]
        else:
            self.nodes = [(bond.maturity_date, 1) for bond, _ in self.bonds_weight]
        self.nodes.sort()
    
    def get_solver_error(self, values: list[float]) -> float:
        curve = self.spread_curve
        curve.update_nodes(log_values=values)
        err = 0
        for bond, wi in self.bonds_weight:
            err += wi * (bond.get_price_from_curve(self.date, curve) - bond.price(self.date)) ** 2
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
        for bond, wi in self.bonds_weight:
            price_error = wi * (bond.get_price_from_curve(self.date, curve) - bond.price(self.date))
            price_prime = np.zeros(len(values), dtype=float)
            n_id = 0
            for cshf in bond.get_cashflows(self.date):
                cshf_pv = cshf.amount * curve.get_df(cshf.date)
                while n_id < len(nodes)-2 and cshf.date > nodes[n_id+1].date:
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
        base_curve = self.base_curve()
        self.spread_curve = SpreadCurve(base_curve.date, self.nodes, base_curve,
                                        interpolation_methods=[(None, 'LogLinear')],
                                        _daycount_type=base_curve._daycount_type,
                                        _calendar=base_curve._calendar,
                                        name=self.name)
        CurveContext().update_bond_curve(self.spread_curve)
        return self.build_solver()
