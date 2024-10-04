
from pydantic.dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from typing import ClassVar

from common.chrono import Tenor, Frequency, BDayAdjust, BDayAdjustType
from common.chrono.daycount import DayCount
from common.currency import Currency
from instruments.fixing import RateFixing, RateFixingType


@dataclass(frozen=True)
class NotionalExchangeType(StrEnum):

    NONE = 'NONE'
    INITIAL_FINAL = 'INITIAL_FINAL'
    FINAL = 'FINAL'

    @property
    def final(self) -> bool:
        match self.value:
            case 'INITIAL_FINAL' | 'FINAL':
                return True
        return False

    @property
    def initial(self) -> bool:
        match self.name:
            case 'INITIAL_FINAL':
                return True
        return False


@dataclass(frozen=True)
class SwapLegConvention:
    _currency: str
    _coupon_frequency: str
    _daycount_type: str
    _coupon_calendar: str
    _coupon_adjust_type: str
    _coupon_pay_delay: str
    # _coupon_pay_calendar: str

    _notional_exchange_type: str = field(kw_only=True, default='NONE')
    # _notional_pay_delay: str = None
    # _notional_pay_calendar: str = None

    @property
    def currency(self):
        return Currency(self._currency)
    
    @property
    def coupon_frequency(self):
        return Frequency(self._coupon_frequency)
    
    @property
    def daycount_type(self):
        return DayCount(self._daycount_type)
    
    def coupon_adjust(self):
        return BDayAdjust(BDayAdjustType(self._coupon_adjust_type), self._coupon_calendar)
    
    def coupon_pay_delay(self):
        return Tenor((self._coupon_pay_delay, self._coupon_calendar))
    
    @property
    def notional_exchange(self):
        return NotionalExchangeType(self._notional_exchange_type)

@dataclass(frozen=True)
class SwapFixLegConvention(SwapLegConvention):
    pass

@dataclass(frozen=True)
class SwapFloatLegConvention(SwapLegConvention):
    _fixing_id: str
    _fixing_type: str
    _fixing_lag: str
    _fixing_calendar: str | None = None
    _reset_frequency: str | None = None
    
    def __post_init__(self):
        self.__dict__['fixing'] = RateFixing(RateFixingType(self._fixing_type), name=self._fixing_id)
    
    def fixing_lag(self):
        fixing_calendar = self._fixing_calendar if self._fixing_calendar else self._coupon_calendar
        return Tenor((self._fixing_lag, fixing_calendar))
    
    def reset_frequency(self):
        return Frequency(self._reset_frequency)
    
    def is_interim_reset(self) -> bool:
        return self._fixing_type == RateFixingType.IBOR and self._reset_frequency \
            and self._reset_frequency != self._coupon_frequency


# https://stackoverflow.com/questions/53756788/how-to-set-the-value-of-dataclass-field-in-post-init-when-frozen-true
@dataclass(frozen=True)
class SwapConvention:
    _code: str
    _spot_delay: str
    _spot_calendar: str
    _leg1: SwapLegConvention
    _leg2: SwapLegConvention
    
    def spot_delay(self):
        return Tenor((self._spot_delay, self._spot_calendar))
    
    @property
    def leg1(self):
        return self._leg1
    
    @property
    def leg2(self):
        return self._leg2
    
    def is_basis(self):
        return isinstance(self._leg1, SwapFloatLegConvention) and isinstance(self._leg2, SwapFloatLegConvention)
