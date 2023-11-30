
import pandas as pd
from sortedcontainers import SortedDict

from . import core as data_core
from .scraper import CME_DATE_FORMAT
from lib.base_types import FixingCurve
from model.rate_future import RateFutureIMM, RateFutureSerial
from model.swap_convention import SwapLegConvention

DATA_FOLDER = data_core.DATA_FOLDER
DATE_FORMAT = CME_DATE_FORMAT


def read_fixings(filename: str, date_col: str, rate_col: str) -> FixingCurve:
    df = pd.read_csv(data_core.data_path(filename))
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
                     name_col: str,
                     expiry_col: str,
                     settle_col: str) -> list[RateFutureIMM]:
    df = pd.read_csv(data_core.data_path(filename), dtype=str)
    for col in [expiry_col, settle_col]:
        df[col] = pd.to_datetime(df[col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    df_imm = df[df[expiry_col].apply(lambda d: d.month % 3==0)]
    expiries = []
    for i in range(1, len(df_imm)):
        row = df_imm.iloc[i]
        expiries.append(RateFutureIMM(
            underlying,
            _expiry=row[expiry_col],
            _settle=row[settle_col],
            _rate_start=df_imm.iloc[i-1][settle_col],
            name=row[name_col],
        ))

    return expiries

def read_serial_futures(filename: str,
                        underlying: str,
                        name_col: str,
                        expiry_col: str,
                        settle_col: str) -> list[RateFutureSerial]:
    df = pd.read_csv(data_core.data_path(filename), dtype=str)
    for col in [expiry_col, settle_col]:
        df[col] = pd.to_datetime(df[col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    expiries = [RateFutureSerial(
                    underlying,
                    _expiry=r[expiry_col],
                    _settle=r[settle_col],
                    name=r[name_col]) for _, r in df.iterrows()]
    return expiries

def read_meeting_dates(filename: str = 'meetingdates.csv', bank_col: str='Central Bank', date_col: str='Date',
                       filter: str = 'FED') -> list[pd.Timestamp]:
    df = pd.read_csv(data_core.data_path(filename), dtype=str)
    df[date_col] = pd.to_datetime(df[date_col], format = DATE_FORMAT).apply(lambda tms: tms.date())
    return df[df[bank_col]==filter][date_col].to_list()


def read_swap_conventions(filename: str = 'swap_convention.csv') -> dict[tuple[str, int], SwapLegConvention]:
    df = pd.read_csv(data_core.data_path(filename), dtype=str, index_col=['Name', 'LegId'])
    res = {}
    for id in df.index:
        df_row = df.loc[id]
        kwargs = {}
        if df_row['Type'] == 'FLOAT':
            kwargs['_fixing_lag']=df_row['FixingLag']
            if pd.notna(df_row['ResetFrequency']):
                kwargs['_reset_frequency']=df_row['ResetFrequency']
        res[id] = SwapLegConvention(
            _currency=df_row['Currency'],
            _spot_delay=df_row['SpotDelay'],
            _spot_calendar=df_row['SpotCalendar'],
            _coupon_frequency=df_row['CouponFrequency'],
            _daycount_type=df_row['DayCountType'],
            # _coupon_calendar=df_row['CouponCalendar'],
            _coupon_adjust_type=df_row['CouponAdjustType'],
            _coupon_pay_delay=df_row['CouponPayDelay'],
            **kwargs,
        )
    return res
