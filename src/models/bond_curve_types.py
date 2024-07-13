
from enum import StrEnum, auto

class BondCurveModelType(StrEnum):
    NS = auto()
    NP = auto()

class BondCurveWeightType(StrEnum):
    OTR = 'OTR'
    BidAsk = 'BidAsk'
    Equal = 'Equal'
