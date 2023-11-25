
from pydantic.dataclasses import dataclass
from enum import StrEnum

@dataclass(frozen=True)
class Currency(StrEnum):

    USD = 'USD'
    EUR = 'EUR'
    GBP = 'GBP'
    JPY = 'JPY'
    CAD = 'CAD'
    CHF = 'CHF'
    AUD = 'AUD'
    NZD = 'NZD'
    SEK = 'SEK'
    NOK = 'NOK'
    CNY = 'CNY'
    HKD = 'HKD'
