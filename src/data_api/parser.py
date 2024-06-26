
import pandas as pd
from sortedcontainers import SortedDict

from .cme import DATE_FORMAT
from common import io
from instruments.fixing import Fixing, FixingCurve
from instruments.rate_future import RateFutureIMM, RateFutureSerial
from instruments.swap_convention import SwapLegConvention, SwapFixLegConvention, SwapFloatLegConvention
from instruments.bond_future import BondFuture
from common.chrono import Tenor

NAME_ID = 'productCode'
EXPIRY_ID = 'lastTrade'
SETTLE_ID = 'settlement'


def read_fixings(filename: str, date_col: str, rate_col: str) -> FixingCurve:
    df = pd.read_csv(io.get_path(filename))
    df = df[df[date_col].notnull()]
    df[date_col] = pd.to_datetime(df[date_col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    date_rates = df[[date_col, rate_col]].set_index(date_col).T.to_dict('list')
    res = SortedDict()
    for d, v in date_rates.items():
        assert len(date_rates[d]) == 1
        res[d] = v[0] / 100
    return FixingCurve(res, name=filename.split('.')[0])

def read_IMM_futures(filename: str,
                     underlying: str,
                     name_col: str = NAME_ID,
                     expiry_col: str = EXPIRY_ID,
                     settle_col: str = SETTLE_ID) -> list[RateFutureIMM]:
    df = pd.read_csv(io.get_path(filename), dtype=str)
    for col in [expiry_col, settle_col]:
        df[col] = pd.to_datetime(df[col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    df_imm = df[df[expiry_col].apply(lambda d: d.month % 3==0)]
    expiries = []
    for id in range(1, len(df_imm)):
        row = df_imm.iloc[id]
        expiries.append(RateFutureIMM(
            Fixing(name=underlying),
            _expiry=row[expiry_col],
            _settle=row[settle_col],
            _rate_start_date=df_imm.iloc[id-1][settle_col],
            name=row[name_col],
        ))
    return expiries

def read_serial_futures(filename: str,
                        underlying: str,
                        name_col: str = NAME_ID,
                        expiry_col: str = EXPIRY_ID,
                        settle_col: str = SETTLE_ID) -> list[RateFutureSerial]:
    df = pd.read_csv(io.get_path(filename), dtype=str, comment='#')
    for col in [expiry_col, settle_col]:
        df[col] = pd.to_datetime(df[col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    expiries = [RateFutureSerial(
                    Fixing(name=underlying),
                    _expiry=r[expiry_col],
                    _settle=r[settle_col],
                    name=r[name_col]) for _, r in df.iterrows()]
    return expiries

def read_meeting_dates(filename: str = 'meetingdates.csv', bank_col: str='Central Bank', date_col: str='Date',
                       filter: str = 'FED') -> list[pd.Timestamp]:
    df = pd.read_csv(io.get_path(filename), dtype=str)
    df[date_col] = pd.to_datetime(df[date_col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    return df[df[bank_col]==filter][date_col].to_list()


def read_swap_conventions(filename: str = 'swap_convention.csv') -> dict[tuple[str, int], SwapLegConvention]:
    df = pd.read_csv(io.get_path(filename), dtype=str, index_col=['Name', 'LegId'])
    res = {}
    for id in df.index:
        df_row = df.loc[id]
        kwargs = {
            '_currency': df_row['Currency'],
            '_spot_delay': df_row['SpotDelay'],
            '_spot_calendar': df_row['SpotCalendar'],
            '_coupon_frequency': df_row['CouponFrequency'],
            '_daycount_type': df_row['DayCountType'],
            # '_coupon_calendar': df_row['CouponCalendar'],
            '_coupon_adjust_type': df_row['CouponAdjustType'],
            '_coupon_pay_delay': df_row['CouponPayDelay'],
        }
        if df_row['Type'] == 'FLOAT':
            kwargs['_fixing'] = df_row['Fixing']
            kwargs['_fixing_type'] = df_row['FixingType']
            kwargs['_fixing_lag'] = df_row['FixingLag']
            if pd.notna(df_row['ResetFrequency']):
                kwargs['_reset_frequency'] = df_row['ResetFrequency']
            res[id] = SwapFloatLegConvention(**kwargs)
        else:
            res[id] = SwapFixLegConvention(**kwargs)
    return res

FIRST_DELIVERY_ID = 'firstDelivery'
LAST_DELIVERY_ID = 'lastDelivery'

def read_bond_futures(filename: str,
                    min_tenor: Tenor, max_tenor: Tenor, original_term: float = None,
                    name_col: str = NAME_ID,
                    expiry_col: str = EXPIRY_ID,
                    first_delivery_col: str = FIRST_DELIVERY_ID,
                    last_delivery_col: str = LAST_DELIVERY_ID,
                    **kwargs) -> list[BondFuture]:
    df = pd.read_csv(io.get_path(filename), dtype=str)
    for col in [expiry_col, first_delivery_col, last_delivery_col]:
        df[col] = pd.to_datetime(df[col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    expiries = [BondFuture(
                    _expiry=row[expiry_col],
                    _settle=row[expiry_col],
                    _first_delivery=row[first_delivery_col],
                    _last_delivery=row[last_delivery_col],
                    _min_tenor=min_tenor,
                    _max_tenor=max_tenor,
                    _original_term=original_term,
                    name=row[name_col], **kwargs
                ) for _, row in df.iterrows()]
    return expiries
