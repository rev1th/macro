
from pydantic.dataclasses import dataclass
from typing import ClassVar, Union, Optional
import datetime as dtm
import logging
from copy import deepcopy
import numpy as np
import pandas as pd

from lib import solver
from models.base_types import NamedClass, NamedDatedClass
from common.chrono import DayCount, get_bdate_series
from models.rate_curve_instrument import CurveInstrument
from models.rate_future import RateFutureC
from models.swap import DomesticSwap, BasisSwap
from models.fx import FXSpot, FXSwapC
from models.rate_curve import YieldCurve
from models.vol_curve import VolCurve

CURVE_SOLVER_MAX_ITERATIONS = 10
CURVE_SOLVER_TOLERANCE = 1e-6
DF_UPPER_LIMIT = 1e1
DF_LOWER_LIMIT = 1e-4
CVXADJ_RATE_TOLERANCE = 0.3e-4
EPSILON = 1e-4

logger = logging.Logger(__name__)


@dataclass
class YieldCurveModel(NamedClass):

    _instruments: list[CurveInstrument]
    _interpolation_methods: list[tuple[Optional[Union[dtm.date, int, str]], str]] = None
    _daycount_type: DayCount = None
    _collateral_curve: YieldCurve = None
    _collateral_spot: FXSpot = None
    _rate_vol_curve: VolCurve = None

    _curve: ClassVar[YieldCurve]
    _constructor: ClassVar[NamedDatedClass]
    _knots: ClassVar[list[dtm.date]]

    @property
    def instruments(self) -> list[CurveInstrument]:
        return self._instruments
    
    @property
    def collateral_curve(self) -> YieldCurve:
        return self._collateral_curve
    
    @property
    def collateral_spot(self) -> YieldCurve:
        return self._collateral_spot
    
    @property
    def vol_curve(self) -> VolCurve:
        return self._rate_vol_curve
    
    @property
    def curve(self) -> YieldCurve:
        return self._curve
    
    @property
    def constructor(self):
        return self._constructor
    
    @property
    def knots(self) -> list[dtm.date]:
        return self._knots
    
    def knot_instruments(self) -> list[CurveInstrument]:
        return [inst for inst in self.instruments if inst.knot]
    
    def reset(self, date: dtm.date = None) -> None:
        knot_dates = []
        for ins in self.instruments:
            if ins.knot and (not knot_dates or knot_dates[-1] != ins.knot):
                knot_dates.append(ins.knot)
        self._knots = knot_dates
        if date:
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
            self._curve = YieldCurve(
                date,
                [(k, 1) for k in self.knots],
                _calendar = self.constructor._calendar,
                name=f"{self.constructor.name}-{self.name}",
                **kwargs
            )
            if self.vol_curve:
                self.set_convexity()
        else:
            self._curve = None
    
    def get_calibration_summary(self) -> pd.DataFrame:
        return pd.DataFrame(
            [(ins.name, ins.knot, ins.price, self.get_instrument_pv(ins)) for ins in self.instruments],
            columns=['Name', 'Date', 'Price', 'Error']
            )
    
    def get_instrument_pv(self, instrument: CurveInstrument) -> float:
        if isinstance(instrument, FXSwapC):
            return instrument.get_pv(self.curve, ref_discount_curve=self.collateral_curve, spot=self.collateral_spot)
        elif self != self.constructor.models[0]:
            if isinstance(instrument, DomesticSwap):
                return instrument.get_pv(forecast_curve=self.curve, discount_curve=self.constructor.models[0].curve)
            elif isinstance(instrument, BasisSwap):
                return instrument.get_pv(leg1_forecast_curve=self.curve, discount_curve=self.constructor.models[0].curve)
            else:
                return instrument.get_pv(self.curve)
        else:
            return instrument.get_pv(self.curve)
    
    def get_bootstrap_knot_error(self, value: float, date: dtm.date) -> float:
        self.curve.update_node(date, value)
        knot_ins = [ins for ins in self.instruments if ins.knot == date]
        assert len(knot_ins) > 0, logger.critical(f'No instruments to solve knot {date}')
        return self.get_instrument_pv(knot_ins[-1])
    
    def set_convexity(self) -> None:
        for f_ins in self.instruments:
            if isinstance(f_ins, RateFutureC):
                f_ins.set_convexity(self.vol_curve)
        return
    
    def calibrate_convexity(self, last_fixed_vol_date: dtm.date = None) -> None:
        self.constructor.build()

        if last_fixed_vol_date is None:
            last_fixed_vol_date = self.constructor.date
        for sw_ins in self.instruments:
            if isinstance(sw_ins, DomesticSwap) and sw_ins.exclude_knot and sw_ins.end_date > last_fixed_vol_date:
                fut_implied_par = sw_ins.get_par(self.curve)
                sw_crv_diff = fut_implied_par - sw_ins.fix_rate
                last_fixed_vol = self.vol_curve.get_vol(last_fixed_vol_date)
                logger.critical(f'{sw_ins.name} Implied Rate={fut_implied_par}, Market Rate={sw_ins.fix_rate}')
                if abs(sw_crv_diff) > CVXADJ_RATE_TOLERANCE and last_fixed_vol > 0:
                    sw_dcf_1 = self.curve.get_dcf(self.curve.date, last_fixed_vol_date)
                    sw_dcf_2 = self.curve.get_dcf(self.curve.date, sw_ins.end_date)
                    pv01_unit = sw_ins.get_pv01(self.curve) * 10000 / sw_ins.notional
                    var_offset = np.log(1 + sw_crv_diff * pv01_unit / self.curve.get_df(sw_ins.end_date)) *\
                                    12 / (2*sw_dcf_2**3 - 3*sw_dcf_1*sw_dcf_2**2 + sw_dcf_1**3)
                    # var_offset = sw_crv_diff * 12 * sw_dcf_2 / (2*sw_dcf_2**3 - 3*sw_dcf_1*sw_dcf_2**2 + sw_dcf_1**3)
                    var_adjusted = np.square(last_fixed_vol) + var_offset
                    vol_adjusted = np.sqrt(var_adjusted) if var_adjusted > 0 else 0
                    logger.critical(f'Rate Vol Adjusted {sw_ins.end_date} {vol_adjusted}')
                    self.vol_curve.update_node(last_fixed_vol_date, vol_adjusted)
                    return self.constructor.calibrate_convexity(last_fixed_vol_date)
                else:
                    last_fixed_vol_date = sw_ins.end_date
                    self.vol_curve.add_node(last_fixed_vol_date, last_fixed_vol)
        return


@dataclass
class YieldCurveGroupModel(NamedDatedClass):
    _models: list[YieldCurveModel]
    _calendar: str = ''

    def __post_init__(self):
        for crv_mod in self._models:
            crv_mod._constructor = self
    
    @property
    def models(self) -> list[YieldCurveModel]:
        return self._models
    
    @property
    def curves(self) -> list[YieldCurve]:
        return [crv_mod.curve for crv_mod in self.models]
    
    def get_bootstrap_knots(self) -> list[dtm.date]:
        knot_dates = set()
        for crv_mod in self.models:
            knot_dates = knot_dates.union(crv_mod.knots)
        return sorted(list(knot_dates))
    
    def build_bootstrap(self, iter: int = 1) -> bool:
        nodes_in = [deepcopy(crv_mod.curve.nodes) for crv_mod in self.models]
        for k in self.get_bootstrap_knots():
            for crv_mod in self.models:
                if k not in crv_mod.knots:
                    continue
                solver.find_root(
                    crv_mod.get_bootstrap_knot_error,
                    args=(k,),
                    bracket=[DF_LOWER_LIMIT, DF_UPPER_LIMIT]
                )
        for i, crv_mod in enumerate(self.models):
            error = 0
            for j, nd in enumerate(crv_mod.curve.nodes):
                assert nodes_in[i][j].date == nd.date, f"Unexpected nodes mismatch {nodes_in[i][j]} {nd}"
                error += abs(nodes_in[i][j].discountfactor - nd.discountfactor)
            if error > CURVE_SOLVER_TOLERANCE:
                if iter >= CURVE_SOLVER_MAX_ITERATIONS:
                    logger.error(f"Failed to fit the curve after {CURVE_SOLVER_MAX_ITERATIONS}.\n {nodes_in}")
                    return False
                return self.build_bootstrap(iter=iter+1)
        return True
    
    def set_nodes(self, log_values: list[float]):
        knot_lens_sum = [0]
        for crv_mod in self.models:
            knot_lens_sum.append(knot_lens_sum[-1] + len(crv_mod.knots))
            crv_mod.curve.update_nodes(log_values[knot_lens_sum[-2] : knot_lens_sum[-1]])
        return
    
    def get_solver_error(self, log_values: list[float]) -> float:
        errors = []
        self.set_nodes(log_values)
        for crv_mod in self.models:
            for ins in crv_mod.knot_instruments():
                errors.append(crv_mod.get_instrument_pv(ins))
        return np.sqrt(np.mean(np.array(errors)**2))
    
    def get_jacobian(self, log_values: list[float] = None) -> list[float]:
        self.set_nodes(log_values)

        knot_count = len(log_values)
        instr_count = sum([len(crv_mod.knot_instruments()) for crv_mod in self.models])
        pvs = np.zeros(instr_count)
        pvs_up = np.zeros((knot_count, instr_count))
        kn, ki = 0, 0
        for crv_mod in self.models:
            for inst in crv_mod.knot_instruments():
                pvs[ki] = crv_mod.get_instrument_pv(inst)
                ki += 1
            
            for knot in crv_mod.knots:
                df = crv_mod.curve.get_df(knot)
                df_up = df * np.exp(EPSILON)
                crv_mod.curve.update_node(knot, df_up)
                
                kj = 0
                for crv_mod_j in self.models:
                    for inst in crv_mod_j.knot_instruments():
                        # if knot <= inst.knot:
                        pvs_up[kn][kj] = crv_mod_j.get_instrument_pv(inst)
                        kj += 1
                # df_down = df * np.exp(-EPSILON)
                # crv_mod.curve.update_node(kn, df_down)
                crv_mod.curve.update_node(knot, df)
                kn += 1

        gradient = np.zeros(knot_count)
        for kn in range(knot_count):
            gradient[kn] = np.mean((pvs_up[kn] - pvs) * pvs) / EPSILON
            # gradient[kn] = np.mean((pvs_up[kn] - pvs_down[kn]) * pvs) / (2*EPSILON)
        gradient /= np.sqrt(np.mean(pvs*pvs))
        return gradient
    
    def build_solver(self) -> bool:
        knot_count = sum([len(crv_mod.knots) for crv_mod in self.models])
        init_guess = np.zeros(knot_count, dtype=float)
        res = solver.find_fit(cost_f=self.get_solver_error,
                              init_guess=init_guess,
                              jacobian=self.get_jacobian)
        self.set_nodes(res.x)
        return True
    
    def build(self) -> bool:
        for crv_mod in self.models:
            crv_mod.reset(self.date)
        # return self.build_solver()
        return self.build_bootstrap()
    
    def calibrate_convexity(self, last_fixed_vol_date: dtm.date = None) -> None:
        for con in self.models:
            con.calibrate_convexity(last_fixed_vol_date=last_fixed_vol_date)
        return
    
    def get_calibration_summary(self) -> list[pd.DataFrame]:
        return pd.concat([con.get_calibration_summary() for con in self.models])
    
    def get_graph_info(self) -> tuple[dict[str, int], dict[str, int]]:
        fwd_rates = {}
        node_zrates = {}
        for yc in self.curves:
            bdates = get_bdate_series(self.date, yc.nodes[-1].date, self._calendar)
            fwd_rates_i = {}
            node_zrates_i = {}
            for id, dt in enumerate(bdates[:-1]):
                fwd_rates_i[dt] = yc.get_forward_rate(dt, bdates[id+1])
            for nd in yc._nodes:
                node_zrates_i[nd.date] = yc.get_zero_rate(nd.date)
            fwd_rates[yc.name] = pd.Series(fwd_rates_i)
            node_zrates[yc.name] = pd.Series(node_zrates_i)
        return fwd_rates, node_zrates

