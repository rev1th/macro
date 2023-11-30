
from pydantic.dataclasses import dataclass
from enum import Enum

from lib.date_utils import Tenor, Frequency, DayCount, BDayAdjust
from .currency import Currency


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


@dataclass
class SwapLegConvention():
    _currency: str
    _spot_delay: str
    _spot_calendar: str
    _coupon_frequency: str
    _daycount_type: str
    # _coupon_calendar: str
    _coupon_adjust_type: str
    _coupon_pay_delay: str
    # _coupon_pay_calendar: str = None
    _reset_frequency: str = None

    _fixing_lag: str = '0B'
    _fixing_calendar: str = None
    
    _notional_exchange_type: str = 'NONE'
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
    def coupon_adjust_type(self):
        return BDayAdjust(self._coupon_adjust_type, self._spot_calendar)
    
    @property
    def coupon_pay_delay(self):
        return Tenor((self._coupon_pay_delay, self._spot_calendar))
    
    @property
    def reset_frequency(self):
        return Frequency(self._reset_frequency)
    
    @property
    def fixing_calendar(self):
        return self._fixing_calendar if self._fixing_calendar else self._spot_calendar

    @property
    def fixing_lag(self):
        return Tenor((self._fixing_lag, self.fixing_calendar))
    
    @property
    def notional_exchange(self):
        return NotionalExchangeType(self._notional_exchange_type)


@dataclass(frozen=True)
class SwapConvention():
    _code: str
    _leg1: SwapLegConvention = None
    _leg2: SwapLegConvention = None
    
    # https://stackoverflow.com/questions/53756788/how-to-set-the-value-of-dataclass-field-in-post-init-when-frozen-true
    def __post_init__(self):
        for k, v in SWAP_CONVENTION_MAP.items():
            if k[0] == self._code:
                if k[1] == 1:
                    object.__setattr__(self, '_leg1', v)
                elif k[1] == 2:
                    object.__setattr__(self, '_leg2', v)
                else:
                    raise Exception(f'Invalid leg id found {v}')
        # leg_codes = self._code.split('-')
        # leg_codes_sub = [c.split('_') for c in leg_codes]
        # if len(leg_codes_sub) == 1:
        #     leg_codes_sub = [[leg_codes_sub[0][0]]] + leg_codes_sub
        # return leg_codes_sub

    @property
    def leg1(self):
        return self._leg1

    @property
    def leg2(self):
        return self._leg2

SWAP_CONVENTION_MAP: dict[tuple[str, int], SwapLegConvention] = {}
