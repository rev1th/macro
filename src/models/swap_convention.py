
from pydantic.dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Optional

from common.chrono import Tenor, Frequency, DayCount, BDayAdjust, BDayAdjustType
from common.currency import Currency
from models.fixing import Fixing


@dataclass(frozen=True)
class NotionalExchangeType(Enum):

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
    _spot_delay: str
    _spot_calendar: str
    _coupon_frequency: str
    _daycount_type: str
    # _coupon_calendar: str
    _coupon_adjust_type: str
    _coupon_pay_delay: str
    # _coupon_pay_calendar: str = None

    _notional_exchange_type: str = field(kw_only=True, default='NONE')
    # _notional_pay_delay: str = None
    # _notional_pay_calendar: str = None

    @property
    def currency(self):
        return Currency(self._currency)
    
    @property
    def spot_delay(self):
        return Tenor((self._spot_delay, self._spot_calendar))
    
    @property
    def coupon_frequency(self):
        return Frequency(self._coupon_frequency)
    
    @property
    def daycount_type(self):
        return DayCount(self._daycount_type)
    
    @property
    def coupon_adjust(self):
        return BDayAdjust(BDayAdjustType(self._coupon_adjust_type), self._spot_calendar)
    
    @property
    def coupon_pay_delay(self):
        return Tenor((self._coupon_pay_delay, self._spot_calendar))
    
    @property
    def notional_exchange(self):
        return NotionalExchangeType(self._notional_exchange_type)

@dataclass(frozen=True)
class SwapFixLegConvention(SwapLegConvention):
    pass

@dataclass(frozen=True)
class SwapFloatLegConvention(SwapLegConvention):

    _fixing: str
    _fixing_lag: str
    _fixing_calendar: Optional[str] = None
    _fixing_reset_frequency: Optional[str] = None
    
    @property
    def fixing(self):
        return Fixing(self._fixing)
    
    @property
    def fixing_calendar(self):
        return self._fixing_calendar if self._fixing_calendar else self._spot_calendar

    @property
    def fixing_lag(self):
        return Tenor((self._fixing_lag, self.fixing_calendar))
    
    @property
    def fixing_reset_frequency(self):
        return Frequency(self._fixing_reset_frequency)


# https://stackoverflow.com/questions/53756788/how-to-set-the-value-of-dataclass-field-in-post-init-when-frozen-true
@dataclass(frozen=True)
class SwapConvention:
    _code: str
    _leg1: SwapLegConvention = None
    _leg2: SwapLegConvention = None
    
    @property
    def leg1(self):
        return self._leg1

    @property
    def leg2(self):
        return self._leg2


SWAP_CONVENTION_MAP: dict[str, SwapConvention] = {}

def add_swap_convention(name: str, leg_id: int, leg_conv: SwapLegConvention) -> None:
    kwargs = {}
    if name in SWAP_CONVENTION_MAP:
        if leg_id == 1:
            kwargs = {'_leg1': leg_conv, '_leg2': SWAP_CONVENTION_MAP[name].leg2}
        elif leg_id == 2:
            kwargs = {'_leg1': SWAP_CONVENTION_MAP[name].leg1, '_leg2': leg_conv}
        else:
            raise Exception(f'Invalid leg id found {leg_id}')
    else:
        if leg_id == 1:
            kwargs = {'_leg1': leg_conv}
        elif leg_id == 2:
            kwargs = {'_leg2': leg_conv}
        else:
            raise Exception(f'Invalid leg id found {leg_id}')
    SWAP_CONVENTION_MAP[name] = SwapConvention(name, **kwargs)

def get_swap_convention(name: str):
    return SWAP_CONVENTION_MAP[name]
