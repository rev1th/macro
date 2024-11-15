from pydantic.dataclasses import dataclass
from typing import ClassVar, Union, Optional
import datetime as dtm
import logging
from copy import deepcopy
import numpy as np
import pandas as pd

from common.base_class import NameClass, NameDateClass
from common.chrono.tenor import get_bdate_series, Calendar
from common.chrono.daycount import DayCount
from common.numeric import solver
from instruments.rate_curve_instrument import CurveInstrument
from instruments.fx import FXSpot, FXCurve
from instruments.rate_curve import RateCurve, SpreadCurve
from instruments.vol_curve import VolCurve
from models.curve_context import CurveContext

CURVE_SOLVER_MAX_ITERATIONS = 10
CURVE_SOLVER_TOLERANCE = 1e-6
DF_UPPER_LIMIT = 1e1
DF_LOWER_LIMIT = 1e-4
EPSILON = 1e-4

logger = logging.Logger(__name__)


@dataclass
class RateCurveModel(NameClass):

    _instruments: list[CurveInstrument]
    _interpolation_methods: list[tuple[Optional[Union[dtm.date, int, str]], str]] = None
    _daycount_type: DayCount = None
    _collateral_curve_id: Optional[str] = None
    _collateral_spot: Optional[FXSpot] = None
    _rate_vol_curve: Optional[VolCurve] = None
    _spread_from: Optional[str] = None

    _curve: ClassVar[RateCurve]
    _constructor: ClassVar[NameDateClass]
    _nodes: ClassVar[list[dtm.date]]
    _nodes_instruments: ClassVar[dict[dtm.date, list[CurveInstrument]]]
    _collateral_curve: ClassVar[RateCurve] = None

    def __post_init__(self):
        nodes_instruments = {}
        for ins in self._instruments:
            if not ins.exclude_fit:
                nodes_instruments.setdefault(ins.node, []).append(ins)
        self._nodes = sorted(nodes_instruments.keys())
        self._nodes_instruments = nodes_instruments
    
    @property
    def curve(self) -> RateCurve:
        return self._curve
    
    @property
    def date(self) -> dtm.date:
        return self._constructor.date
    
    def node_instruments(self) -> list[CurveInstrument]:
        return [inst for inst in self._instruments if not inst.exclude_fit]
    
    def reset(self, date: dtm.date) -> None:
        kwargs = {}
        if self._interpolation_methods:
            for id, interp in enumerate(self._interpolation_methods):
                if isinstance(interp[0], str):
                    for inst_id, inst in enumerate(self.node_instruments()):
                        if inst.name == interp[0]:
                            self._interpolation_methods[id] = (inst_id, interp[1])
                            break
            kwargs['interpolation_methods'] = self._interpolation_methods
        if self._daycount_type:
            kwargs['_daycount_type'] = self._daycount_type
        if self._collateral_curve_id:
            self._collateral_curve = CurveContext().get_rate_curve_last(self._collateral_curve_id, self.date)
        if self._spread_from:
            curve_obj = SpreadCurve
            kwargs['_base_curve'] = CurveContext().get_rate_curve(self._spread_from, self.date)
        elif self._collateral_spot:
            curve_obj = FXCurve
            kwargs['_spot'] = self._collateral_spot
            kwargs['_domestic_curve'] = self._collateral_curve
        else:
            curve_obj = RateCurve
        self._curve = curve_obj(
            date,
            [(k, 1) for k in self._nodes],
            _calendar = self._constructor._calendar,
            name=f"{self._constructor.name}-{self.name}",
            **kwargs
        )
        CurveContext().update_rate_curve(self._curve)
        if self._rate_vol_curve:
            self.set_convexity()
    
    def get_calibration_summary(self):
        return pd.DataFrame(
            [(self.date, self.name, ins.name, ins.end, ins.underlier.data[self.date], ins.node,
                self.get_instrument_pv(ins)) for ins in self._instruments],
            columns=['Date', 'Curve', 'Instrument', 'End Date', 'Price', 'Node', 'Error']
        )
    
    def get_nodes_summary(self):
        nodes = [self.date] + self._nodes
        fwd_rates = []
        prev_rate = None
        for id in range(len(nodes)):
            rate = self._curve.get_forward_rate(nodes[id], nodes[id] + dtm.timedelta(days=1))
            fwd_rates.append((nodes[id], rate, rate-prev_rate if prev_rate else None))
            prev_rate = rate
        return pd.DataFrame(
            [(self.date, self.name, node, rate, change) for node, rate, change in fwd_rates],
            columns=['Date', 'Curve', 'Node', 'Rate', 'Change']
        )
    
    def get_instrument_pv(self, instrument: CurveInstrument) -> float:
        return instrument.get_pv(self.curve, self._collateral_curve, self._collateral_spot)
    
    def get_bootstrap_node_error(self, value: float, date: dtm.date) -> float:
        self._curve.update_node(date, value)
        node_insts = self._nodes_instruments[date]
        assert len(node_insts) > 0, f'No instruments to solve node {date}'
        return self.get_instrument_pv(node_insts[-1])
    
    def get_solver_node_error(self, values: list[float], date: dtm.date) -> float:
        self._curve.update_node(date, np.exp(values[0]))
        node_insts = self._nodes_instruments[date]
        errors = np.zeros(len(node_insts))
        for ki, ins in enumerate(node_insts):
            errors[ki] = self.get_instrument_pv(ins)
        return np.sqrt(np.mean(errors**2))
    
    def get_jacobian_node(self, values: list[float], date: dtm.date) -> list[float]:
        node_insts = self._nodes_instruments[date]
        pvs = np.zeros(len(node_insts))
        self._curve.update_node(date, np.exp(values[0]))
        for ki, inst in enumerate(node_insts):
            pvs[ki] = self.get_instrument_pv(inst)
        
        dvalue = self._curve.get_dcf(date) * EPSILON
        pvs_up = np.zeros(len(node_insts))
        value_up = values[0] + dvalue
        self._curve.update_node(date, np.exp(value_up))
        for ki, inst in enumerate(node_insts):
            pvs_up[ki] = self.get_instrument_pv(inst)
        # pvs_down = np.zeros(len(node_insts))
        # value_down = values[0] - dvalue
        # self._curve.update_node(date, np.exp(value_down))
        # for ki, inst in enumerate(node_insts):
        #     pvs_down[ki] = self.get_instrument_pv(inst)

        gradient = 2 * np.mean((pvs_up - pvs) * pvs) / (np.sqrt(np.mean(pvs*pvs)) * EPSILON)
        # gradient = np.mean((pvs_up - pvs_down) * pvs) / (np.sqrt(np.mean(pvs*pvs)) * 2 * dvalue)
        return np.array(gradient)
    
    def solve_node(self, date: dtm.date) -> bool:
        if False: # len(self._nodes_instruments[date]) > 1:
            solver.find_fit(
                cost_f=self.get_solver_node_error,
                args=(date,), init_guess=0.0, tol=100,
                jacobian=self.get_jacobian_node)
        else:
            solver.find_root(
                self.get_bootstrap_node_error,
                args=(date,),
                bracket=[DF_LOWER_LIMIT, DF_UPPER_LIMIT]
            )
        return True
    
    def set_convexity(self) -> None:
        for f_ins in self._instruments:
            f_ins.set_convexity(self._rate_vol_curve)
        return
    
    def calibrate_convexity(self, node_vol_date: dtm.date = None) -> None:
        self._constructor.build_simple()
        if node_vol_date is None:
            node_vol_date = self.date
        for inst in self._instruments:
            if inst.is_convexity_swap(node_vol_date):
                node_vol = self._rate_vol_curve.get_node(node_vol_date)
                vol_adjusted = inst.get_convexity_adjustment(
                    self._curve, node_vol_date, node_vol, self._collateral_curve)
                if vol_adjusted is not None and node_vol != vol_adjusted:
                    self._rate_vol_curve.update_node(node_vol_date, vol_adjusted)
                    return self.calibrate_convexity(node_vol_date)
                else:
                    node_vol_date = inst.end
                    self._rate_vol_curve.add_node(node_vol_date, node_vol)
        return


@dataclass
class RateCurveGroupModel(NameDateClass):
    _models: list[RateCurveModel]
    _calendar: Calendar

    def __post_init__(self):
        for crv_model in self._models:
            crv_model._constructor = self
    
    @property
    def models(self) -> list[RateCurveModel]:
        return self._models
    
    @property
    def curves(self) -> list[RateCurve]:
        return [crv_model.curve for crv_model in self.models]
    
    def get_bootstrap_nodes(self) -> list[dtm.date]:
        node_dates = set()
        for crv_model in self.models:
            node_dates = node_dates.union(crv_model._nodes)
        return sorted(list(node_dates))
    
    def build_bootstrap(self, iter: int = 1) -> bool:
        nodes_in = [deepcopy(crv_model.curve.nodes) for crv_model in self.models]
        for k in self.get_bootstrap_nodes():
            for crv_model in self.models:
                if k not in crv_model._nodes:
                    continue
                crv_model.solve_node(k)
        for i, crv_model in enumerate(self.models):
            error = 0
            for j, nd in enumerate(crv_model.curve.nodes):
                assert nodes_in[i][j].date == nd.date, f"Unexpected nodes mismatch {nodes_in[i][j]} {nd}"
                error += abs(nodes_in[i][j].value - nd.value)
            if error > CURVE_SOLVER_TOLERANCE:
                if iter >= CURVE_SOLVER_MAX_ITERATIONS:
                    logger.error(f"Failed to fit the curve after {CURVE_SOLVER_MAX_ITERATIONS}.\n {nodes_in}")
                    return False
                return self.build_bootstrap(iter=iter+1)
        return True
    
    def set_nodes(self, log_values: list[float]):
        node_lens_sum = [0]
        for crv_model in self.models:
            node_lens_sum.append(node_lens_sum[-1] + len(crv_model._nodes))
            crv_model.curve.update_nodes(log_values[node_lens_sum[-2] : node_lens_sum[-1]])
        return
    
    def get_solver_error(self, log_values: list[float]) -> float:
        errors = []
        self.set_nodes(log_values)
        for crv_model in self.models:
            for ins in crv_model.node_instruments():
                errors.append(crv_model.get_instrument_pv(ins))
        return np.sqrt(np.mean(np.array(errors)**2))
    
    def get_jacobian(self, log_values: list[float] = None) -> list[float]:
        self.set_nodes(log_values)
        node_count = len(log_values)
        inst_count = sum([len(crv_model.node_instruments()) for crv_model in self.models])
        pvs = np.zeros(inst_count)
        pvs_up = np.zeros((node_count, inst_count))
        kn, ki = 0, 0
        for crv_model in self.models:
            for inst in crv_model.node_instruments():
                pvs[ki] = crv_model.get_instrument_pv(inst)
                ki += 1
            
            for node in crv_model._nodes:
                df = crv_model.curve.get_df(node)
                df_up = df * np.exp(EPSILON)
                crv_model.curve.update_node(node, df_up)
                
                kj = 0
                for crv_model_j in self.models:
                    for inst in crv_model_j.node_instruments():
                        # if node <= inst.node:
                        pvs_up[kn][kj] = crv_model_j.get_instrument_pv(inst)
                        kj += 1
                # df_down = df * np.exp(-EPSILON)
                # crv_model.curve.update_node(kn, df_down)
                crv_model.curve.update_node(node, df)
                kn += 1

        gradient = np.zeros(node_count)
        for kn in range(node_count):
            gradient[kn] = np.mean((pvs_up[kn] - pvs) * pvs) / EPSILON
            # gradient[kn] = np.mean((pvs_up[kn] - pvs_down[kn]) * pvs) / (2*EPSILON)
        gradient /= np.sqrt(np.mean(pvs*pvs))
        return gradient
    
    def build_solver(self) -> bool:
        node_count = sum([len(crv_model._nodes) for crv_model in self.models])
        init_guess = np.zeros(node_count, dtype=float)
        res = solver.find_fit(cost_f=self.get_solver_error,
                              init_guess=init_guess,
                              jacobian=self.get_jacobian)
        self.set_nodes(res)
        return True
    
    def build_simple(self) -> bool:
        for crv_model in self.models:
            crv_model.reset(self.date)
        # return self.build_solver()
        return self.build_bootstrap()
    
    def calibrate_convexity(self, node_vol_date: dtm.date = None) -> None:
        for con in self.models:
            con.calibrate_convexity(node_vol_date=node_vol_date)
        return
    
    def build(self, calibrate_convexity: bool = False) -> bool:
        if calibrate_convexity:
            return self.calibrate_convexity()
        else:
            return self.build_simple()
    
    def get_calibration_summary(self) -> list[pd.DataFrame]:
        return pd.concat([con.get_calibration_summary() for con in self.models])
    
    def get_nodes_summary(self):
        return pd.concat([con.get_nodes_summary() for con in self.models])
    
    def get_graph_info(self) -> tuple[dict[str, int], dict[str, int]]:
        fwd_rates = {}
        node_zrates = {}
        for yc in self.curves:
            bdates = get_bdate_series(self.date, yc.nodes[-1].date, self._calendar)
            fwd_rates_i = {}
            # node_zrates_i = {}
            for id, dt in enumerate(bdates[:-1]):
                fwd_rates_i[dt] = yc.get_forward_rate(dt, bdates[id+1])
            # for nd in yc._nodes:
            #     node_zrates_i[nd.date] = yc.get_spot_rate(nd.date)
            fwd_rates[yc.display_name()] = pd.Series(fwd_rates_i)
            # node_zrates[yc.display_name()] = pd.Series(node_zrates_i)
        return fwd_rates, node_zrates
