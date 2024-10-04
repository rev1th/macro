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
    _knots: ClassVar[list[dtm.date]]
    _knots_instruments: ClassVar[dict[dtm.date, list[CurveInstrument]]]
    _collateral_curve: ClassVar[RateCurve] = None

    def __post_init__(self):
        knots_instruments = {}
        for ins in self._instruments:
            if not ins.exclude_fit:
                knots_instruments.setdefault(ins.knot, []).append(ins)
        self._knots = sorted(knots_instruments.keys())
        self._knots_instruments = knots_instruments
    
    @property
    def curve(self) -> RateCurve:
        return self._curve
    
    @property
    def date(self) -> dtm.date:
        return self._constructor.date
    
    def knot_instruments(self) -> list[CurveInstrument]:
        return [inst for inst in self._instruments if not inst.exclude_fit]
    
    def reset(self, date: dtm.date) -> None:
        kwargs = {}
        if self._interpolation_methods:
            for id, interp in enumerate(self._interpolation_methods):
                if isinstance(interp[0], str):
                    for inst_id, inst in enumerate(self.knot_instruments()):
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
            [(k, 1) for k in self._knots],
            _calendar = self._constructor._calendar,
            name=f"{self._constructor.name}-{self.name}",
            **kwargs
        )
        CurveContext().update_rate_curve(self._curve)
        if self._rate_vol_curve:
            self.set_convexity()
    
    def get_calibration_summary(self):
        return pd.DataFrame(
            [(self.date, self.name, ins.name, ins.end, ins.underlier.data[self.date], ins.knot,
                self.get_instrument_pv(ins)) for ins in self._instruments],
            columns=['Date', 'Curve', 'Instrument', 'End Date', 'Price', 'Node', 'Error']
        )
    
    def get_nodes_summary(self):
        knots = [self.date] + self._knots
        fwd_rates = []
        prev_rate = None
        for id in range(len(knots)):
            rate = self._curve.get_forward_rate(knots[id], knots[id] + dtm.timedelta(days=1))
            fwd_rates.append((knots[id], rate, rate-prev_rate if prev_rate else None))
            prev_rate = rate
        return pd.DataFrame(
            [(self.date, self.name, knot, rate, change) for knot, rate, change in fwd_rates],
            columns=['Date', 'Curve', 'Node', 'Rate', 'Change']
        )
    
    def get_instrument_pv(self, instrument: CurveInstrument) -> float:
        return instrument.get_pv(self.curve, self._collateral_curve, self._collateral_spot)
    
    def get_bootstrap_knot_error(self, value: float, date: dtm.date) -> float:
        self._curve.update_node(date, value)
        knot_ins = self._knots_instruments[date]
        assert len(knot_ins) > 0, logger.critical(f'No instruments to solve knot {date}')
        return self.get_instrument_pv(knot_ins[-1])
    
    def get_solver_knot_error(self, values: list[float], date: dtm.date) -> float:
        self._curve.update_node(date, np.exp(values[0]))
        knot_insts = self._knots_instruments[date]
        errors = np.zeros(len(knot_insts))
        for ki, ins in enumerate(knot_insts):
            errors[ki] = self.get_instrument_pv(ins)
        return np.sqrt(np.mean(errors**2))
    
    def get_jacobian_knot(self, values: list[float], date: dtm.date) -> list[float]:
        knot_insts = self._knots_instruments[date]
        pvs = np.zeros(len(knot_insts))
        self._curve.update_node(date, np.exp(values[0]))
        for ki, inst in enumerate(knot_insts):
            pvs[ki] = self.get_instrument_pv(inst)
        
        dvalue = self._curve.get_val_dcf(date) * EPSILON
        pvs_up = np.zeros(len(knot_insts))
        value_up = values[0] + dvalue
        self._curve.update_node(date, np.exp(value_up))
        for ki, inst in enumerate(knot_insts):
            pvs_up[ki] = self.get_instrument_pv(inst)
        # pvs_down = np.zeros(len(knot_insts))
        # value_down = values[0] - dvalue
        # self._curve.update_node(date, np.exp(value_down))
        # for ki, inst in enumerate(knot_insts):
        #     pvs_down[ki] = self.get_instrument_pv(inst)

        gradient = 2 * np.mean((pvs_up - pvs) * pvs) / (np.sqrt(np.mean(pvs*pvs)) * EPSILON)
        # gradient = np.mean((pvs_up - pvs_down) * pvs) / (np.sqrt(np.mean(pvs*pvs)) * 2 * dvalue)
        return np.array(gradient)
    
    def solve_knot(self, date: dtm.date) -> bool:
        if False: # len(self._knots_instruments[date]) > 1:
            solver.find_fit(
                cost_f=self.get_solver_knot_error,
                args=(date,), init_guess=0.0, tol=100,
                jacobian=self.get_jacobian_knot)
        else:
            solver.find_root(
                self.get_bootstrap_knot_error,
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
    
    def get_bootstrap_knots(self) -> list[dtm.date]:
        knot_dates = set()
        for crv_model in self.models:
            knot_dates = knot_dates.union(crv_model._knots)
        return sorted(list(knot_dates))
    
    def build_bootstrap(self, iter: int = 1) -> bool:
        nodes_in = [deepcopy(crv_model.curve.nodes) for crv_model in self.models]
        for k in self.get_bootstrap_knots():
            for crv_model in self.models:
                if k not in crv_model._knots:
                    continue
                crv_model.solve_knot(k)
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
        knot_lens_sum = [0]
        for crv_model in self.models:
            knot_lens_sum.append(knot_lens_sum[-1] + len(crv_model._knots))
            crv_model.curve.update_nodes(log_values[knot_lens_sum[-2] : knot_lens_sum[-1]])
        return
    
    def get_solver_error(self, log_values: list[float]) -> float:
        errors = []
        self.set_nodes(log_values)
        for crv_model in self.models:
            for ins in crv_model.knot_instruments():
                errors.append(crv_model.get_instrument_pv(ins))
        return np.sqrt(np.mean(np.array(errors)**2))
    
    def get_jacobian(self, log_values: list[float] = None) -> list[float]:
        self.set_nodes(log_values)

        knot_count = len(log_values)
        instr_count = sum([len(crv_model.knot_instruments()) for crv_model in self.models])
        pvs = np.zeros(instr_count)
        pvs_up = np.zeros((knot_count, instr_count))
        kn, ki = 0, 0
        for crv_model in self.models:
            for inst in crv_model.knot_instruments():
                pvs[ki] = crv_model.get_instrument_pv(inst)
                ki += 1
            
            for knot in crv_model._knots:
                df = crv_model.curve.get_df(knot)
                df_up = df * np.exp(EPSILON)
                crv_model.curve.update_node(knot, df_up)
                
                kj = 0
                for crv_model_j in self.models:
                    for inst in crv_model_j.knot_instruments():
                        # if knot <= inst.knot:
                        pvs_up[kn][kj] = crv_model_j.get_instrument_pv(inst)
                        kj += 1
                # df_down = df * np.exp(-EPSILON)
                # crv_model.curve.update_node(kn, df_down)
                crv_model.curve.update_node(knot, df)
                kn += 1

        gradient = np.zeros(knot_count)
        for kn in range(knot_count):
            gradient[kn] = np.mean((pvs_up[kn] - pvs) * pvs) / EPSILON
            # gradient[kn] = np.mean((pvs_up[kn] - pvs_down[kn]) * pvs) / (2*EPSILON)
        gradient /= np.sqrt(np.mean(pvs*pvs))
        return gradient
    
    def build_solver(self) -> bool:
        knot_count = sum([len(crv_model._knots) for crv_model in self.models])
        init_guess = np.zeros(knot_count, dtype=float)
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
