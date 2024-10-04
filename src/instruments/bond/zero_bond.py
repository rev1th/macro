from pydantic.dataclasses import dataclass
import datetime as dtm

from instruments.bond.bond import Bond, BondSettleInfo, BondYieldParameters, CashFlow, FACE_VALUE
from instruments.rate_curve import RateCurve

@dataclass
class ZeroCouponBond(Bond):
    
    def __post_init__(self):
        super().__post_init__()
        self.cashflows = [CashFlow(self._maturity_date, 1)]
    
    def set_data(self, date: dtm.date, price: float):
        super().set_data(date, price)
        self.settle_info[date] = BondSettleInfo(self._settle_delay.get_date(date))
    
    def get_yield(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return yield_params._compounding.get_rate(self.price(date) / FACE_VALUE,
                    yield_params.get_dcf(self.settle_date(date), self.maturity_date))
    
    def get_macaulay_duration(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return yield_params.get_dcf(self.settle_date(date), self.maturity_date)
    
    def get_modified_duration(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        yt = self.get_yield(date, yield_params) * yield_params.get_period_dcf()
        return yield_params.get_dcf(self.settle_date(date), self.maturity_date) / (1 + yt)
    
    def get_dv01(self, date: dtm.date, yield_params = BondYieldParameters()) -> float:
        return self.price(date) * self.get_modified_duration(date, yield_params) * 1e-4
    
    def get_zspread(self, date: dtm.date, curve: RateCurve, yield_params = BondYieldParameters()) -> float:
        return self.get_yield(date) - self._rate_from_curve(self.settle_date(date), self.maturity_date, curve, yield_params)
    
    def get_price_from_curve(self, date: dtm.date, curve: RateCurve) -> float:
        return FACE_VALUE * curve.get_df(self.maturity_date) / curve.get_df(self.settle_date(date))
