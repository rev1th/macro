
from pydantic.dataclasses import dataclass
from dataclasses import InitVar
from typing import ClassVar, Union, Optional, Iterable
import datetime as dtm
import bisect
import logging

from lib.chrono import DayCount, get_bdate_series, date_to_int
from lib.interpolator import Interpolator
from lib import solver
from models.base_types import DataPoint, NamedDatedClass, get_fixing

logger = logging.Logger(__name__)


# https://stackoverflow.com/questions/53990296/how-do-i-make-a-python-dataclass-inherit-hash
@dataclass(frozen=True)
class YieldCurveNode(DataPoint):

    @property
    def discountfactor(self):
        return self.value

# __init__ cannot be overriden so we declare InitVar and assign __post_init__
# https://docs.python.org/3/library/dataclasses.html#init-only-variables
@dataclass
class YieldCurve(NamedDatedClass):
    nodes_init: InitVar[list[tuple[dtm.date, float]]]
    step_cutoff: InitVar[Optional[Union[dtm.date, int]]] = None
    interpolation_method: InitVar[str] = 'Default'

    _daycount_type: DayCount = DayCount.ACT360
    _calendar: str = ''

    _nodes: ClassVar[list[YieldCurveNode]]
    _step_cutoff_date: ClassVar[dtm.date]
    _interpolator: ClassVar[Interpolator]
    _cached_step_rate: ClassVar[dict[tuple[YieldCurveNode, YieldCurveNode], float]]
    _bdates: ClassVar[Iterable[dtm.date]]
    _dcfs_n: ClassVar[dict[dtm.date, float]]
    # https://www.geeksforgeeks.org/python-get-next-key-in-dictionary/

    def __post_init__(self, nodes_init, step_cutoff, interpolation_method: str):
        assert len(nodes_init) > 0, "Cannot build rate curve without nodes"
        assert nodes_init[0][0] > self.date, f"First node {nodes_init[0][0]} should be after valuation date {self.date}"
        self._nodes = [YieldCurveNode(nd[0], nd[1]) for nd in nodes_init]
        self._set_step_cutoff_date(step_cutoff)
        self._interpolator_class = Interpolator.fromString(interpolation_method)
        self._set_interpolator()

        # cached attributes
        self._cached_step_rate = {}
        self._bdates = get_bdate_series(self.date, self._nodes[-1].date, self._calendar)
        self._dcfs_n = {}
        for i, d in enumerate(self._bdates[:-1]):
            self._dcfs_n[d] = self._daycount_type.get_dcf(d, self._bdates[i+1]), i
        self._dcfs_n[self._bdates[-1]] = None, i+1
    
    def _set_step_cutoff_date(self, step_cutoff: Union[int, dtm.date]) -> dtm.date:
        if not step_cutoff:
            self._step_cutoff_date = self.date
        elif isinstance(step_cutoff, int):
            assert step_cutoff >= 0 and step_cutoff < len(self._nodes)
            self._step_cutoff_date = self._nodes[self._step_cutoff].date
        else:
            assert isinstance(step_cutoff, dtm.date), f"{step_cutoff} should be in date format"
            self._step_cutoff_date = step_cutoff
    
    def _set_interpolator(self) -> None:
        knots = [(date_to_int(nd.date), nd.value) for nd in self.nodes if nd.date >= self.step_cutoff_date]
        self._interpolator = self._interpolator_class(knots)
    
    @property
    def nodes(self) -> list[YieldCurveNode]:
        return [YieldCurveNode(self.date, 1)] + self._nodes
    
    @property
    def step_cutoff_date(self) -> dtm.date:
        return self._step_cutoff_date

    def get_dcf_cached(self, date: dtm.date) -> float:
        try:
            return self._dcfs_n[date][0]
        except KeyError:
            return self.get_dcf(date, self._bdates[bisect.bisect_left(self._bdates, date)])

    def get_bdates(self, from_date: dtm.date, to_date: dtm.date) -> list[dtm.date]:
        return [self._bdates[i] for i in range(self._dcfs_n[from_date][1], self._dcfs_n[to_date][1])]

    def get_next_bdate(self, date: dtm.date) -> float:
        try:
            return self._bdates[self._dcfs_n[date][1]+1]
        except KeyError:
            return self._bdates[bisect.bisect_left(self._bdates, date)]

    def update_node(self, date: dtm.date, value: float) -> None:
        for i, node in enumerate(self._nodes):
            if node.date == date:
                self._nodes[i] = YieldCurveNode(date, value)
                self._set_interpolator()
                return
        raise Exception(f"Invalid date {date} to set node")

    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return self._daycount_type.get_dcf(from_date, to_date)

    def get_df(self, date: dtm.date) -> float:
        assert date >= self.date, f"Cannot discount before valuation date {self.date}"
        if date == self.date:
            return 1
        elif date <= self.step_cutoff_date:
            return self._get_step_rate(date, give_df=True)
        
        return self._interpolator.get_value(date_to_int(date))

    def get_rate(self, date: dtm.date) -> float:
        if date < self.step_cutoff_date:
            return self._get_step_rate(date)
        else:
            if date not in self._bdates:
                bdate = self._bdates[bisect.bisect_left(self._bdates, date)-1]
            else:
                bdate = date
            return self.get_forward_rate(bdate, self.get_next_bdate(bdate))
    
    def get_step_df(self, period_rate: float, from_date: dtm.date, to_date: dtm.date) -> float:
        df = 1
        for d in self.get_bdates(from_date, to_date):
            df /= (1 + period_rate * self.get_dcf_cached(d))
        return df
    
    def _step_df_prime(self, period_rate: float, from_date: dtm.date, to_date: dtm.date, _: float) -> float:
        df = 1
        df_mult = 0
        for d in self.get_bdates(from_date, to_date):
            dcf_i = self.get_dcf_cached(d)
            df_i = 1 / (1 + period_rate * dcf_i)
            df_mult -= df_i * dcf_i
            df *= df_i
        return df_mult * df
    
    def _step_df_error(self,
                       period_rate: float,
                       from_date: dtm.date,
                       to_date: dtm.date,
                       period_df: float) -> float:
        return self.get_step_df(period_rate, from_date, to_date) - period_df
    
    def _get_step_rate_period(self, df_period: float, from_date: dtm.date, to_date: dtm.date) -> float:
        dcf_period = self.get_dcf(from_date, to_date)
        dc_period = (to_date - from_date).days
        l_limit = (pow(df_period, -1 / dc_period) - 1) * dc_period / dcf_period
        # u_limit = (1 / df_period - 1) / dcf_period
        return solver.find_root(
                self._step_df_error,
                args=(from_date, to_date, df_period),
                # bracket=[l_limit, u_limit],
                init_guess=l_limit, f_prime=self._step_df_prime,
            )
    
    def _get_step_rate(self, date: dtm.date, give_df: bool = False) -> float:
        assert date >= self.date, f"Cannot determine step rate for {date} < {self.date}"

        step_nodes = [nd for nd in self.nodes if nd.date <= self.step_cutoff_date]
        for i in range(1, len(step_nodes)):
            if date == step_nodes[i].date and give_df:
                return step_nodes[i].discountfactor
            if date < step_nodes[i].date:
                if (step_nodes[i-1], step_nodes[i]) in self._cached_step_rate:
                    step_rate = self._cached_step_rate[(step_nodes[i-1], step_nodes[i])]
                else:
                    df_period = step_nodes[i].discountfactor / step_nodes[i-1].discountfactor
                    step_rate = self._get_step_rate_period(df_period,
                                                           from_date=step_nodes[i-1].date,
                                                           to_date=step_nodes[i].date)
                    self._cached_step_rate[(step_nodes[i-1], step_nodes[i])] = step_rate
                if give_df:
                    return step_nodes[i-1].discountfactor * self.get_step_df(
                            step_rate, step_nodes[i-1].date, date)
                return step_rate
        raise Exception("Out of node bounds for step rate")

    def get_forward_rate(self, from_date: dtm.date, to_date: dtm.date) -> float:
        # assert from_date >= self.date, f"Forward start date {from_date} cannot be before valuation date {self.date}"

        from_df = self.get_df(from_date)
        to_df = self.get_df(to_date)
        return (from_df / to_df - 1) / self.get_dcf(from_date, to_date)

    def get_forecast_rate(self, from_date: dtm.date, to_date: dtm.date, underlying: str = None) -> float:
        assert from_date <= to_date, f"Invalid period to calculate forecast rate {from_date}-{to_date}"

        if from_date < self.date:
            bdates = get_bdate_series(from_date, min(to_date, self.date), self._calendar)
            amount = 1
            for i in range(len(bdates)-1):
                amount *= (1 + get_fixing(underlying, bdates[i]) * self.get_dcf(bdates[i], bdates[i+1]))
            
            if to_date <= self.date:
                return (amount - 1) / self.get_dcf(from_date, self.date)
            else:
                amount *= (1 + self.get_forward_rate(self.date, to_date) * self.get_dcf(self.date, to_date))
                return (amount - 1) / self.get_dcf(from_date, to_date)
        else:
            return self.get_forward_rate(from_date, to_date)
        
    def get_zero_rate(self, date: dtm.date) -> float:
        assert date > self.date, f"{date} should be after valuation date {self.date}"
        try:
            df = self.get_df(date)
            return self._get_step_rate_period(df, self.date, date)
        except Exception as e:
            logger.critical(f"Failed to find zero rate for {date} {e}")
            return None
