import datetime as dtm

from common import sql
from common.models.data_series import DataSeries
from data_api.db_config import META_DB
from data_api import cme_client, nyfed_client
from instruments.fixing import RateFixing, RateFixingType
from instruments.rate_future import RateFutureCompound, RateFutureAverage
from instruments.swap.convention import SwapConvention, SwapFixLegConvention, SwapFloatLegConvention
from instruments.bond_future import BondFuture


def read_fixings(code: str, from_date: dtm.date):
    res = dict()
    for d, v in nyfed_client.get_data(code=code, from_date=from_date):
        res[d] = v / 100
    return RateFixing(RateFixingType.RFR, name=code, _data_series=DataSeries(res))

def read_IMM_futures(code: str) -> list[RateFutureCompound]:
    contracts_list = cme_client.get_futures_contracts(code)
    imm_q_list = [row for row in contracts_list if row[1].month %3==0]
    expiries = []
    for id in range(1, len(imm_q_list)):
        row = imm_q_list[id]
        expiries.append(RateFutureCompound(RateFixing(RateFixingType.RFR, name=row[3]), _expiry=row[1],
                _settle=row[2], _rate_start_date=imm_q_list[id-1][2], _lot_size=row[4], name=row[0]))
    return expiries

def read_serial_futures(code: str) -> list[RateFutureAverage]:
    contracts_list = cme_client.get_futures_contracts(code)
    expiries = [RateFutureAverage(RateFixing(RateFixingType.RFR, name=row[3]), _expiry=row[1], _settle=row[2],
                _lot_size=row[4], name=row[0]) for row in contracts_list]
    return expiries

def read_bond_futures(code: str) -> list[BondFuture]:
    contracts_list = cme_client.get_bond_futures_contracts(code)
    expiries = [BondFuture(_expiry=row[1], _first_delivery=row[2], _last_delivery=row[3],
                name=row[0]) for row in contracts_list]
    return expiries

def read_future_codes(code: str) -> list[str]:
    select_query = f"SELECT future_code FROM futures WHERE underlier_code='{code}'"
    future_codes = sql.fetch(select_query, META_DB)
    return [fc[0] for fc in future_codes]

def read_meeting_dates(code: str) -> list[dtm.date]:
    select_query = f"SELECT date FROM meeting_dates WHERE bank='{code}' ORDER BY date ASC"
    dates_list = sql.fetch(select_query, META_DB)
    return [dtm.datetime.strptime(d, sql.DATE_FORMAT).date() for d, in dates_list]

SWAP_CONV_TABLE = 'swap_conventions'
def read_swap_conventions() -> list[SwapConvention]:
    select_query = f"""SELECT t1.name, t1.spot_delay, t1.spot_calendar, t1.currency,
    t1.leg_type, t1.coupon_frequency, t1.day_count_type, t1.coupon_adjust_type, t1.coupon_pay_delay,
    t1.fixing, t1.fixing_type, t1.fixing_lag, t1.reset_frequency,
    t2.leg_type, t2.coupon_frequency, t2.day_count_type, t2.coupon_adjust_type, t2.coupon_pay_delay,
    t2.fixing, t2.fixing_type, t2.fixing_lag, t2.reset_frequency
    FROM {SWAP_CONV_TABLE} as t1 INNER JOIN {SWAP_CONV_TABLE} as t2
    WHERE t1.name=t2.name AND t1.leg_id=1 AND t2.leg_id=2"""
    select_res = sql.fetch(select_query, META_DB)
    conv_list = []
    for row in select_res:
        name, spot_delay, spot_cal, ccy = row[:4]
        leg_convs = []
        for leg_row in [row[4:13], row[13:]]:
            kwargs = {
                '_currency': ccy,
                '_coupon_frequency': leg_row[1],
                '_daycount_type': leg_row[2],
                '_coupon_calendar': spot_cal,
                '_coupon_adjust_type': leg_row[3],
                '_coupon_pay_delay': leg_row[4],
            }
            if leg_row[0] == 'FLOAT':
                kwargs['_fixing_id'] = leg_row[5]
                kwargs['_fixing_type'] = leg_row[6]
                kwargs['_fixing_lag'] = leg_row[7]
                if leg_row[8]:
                    kwargs['_reset_frequency'] = leg_row[8]
                leg_convs.append(SwapFloatLegConvention(**kwargs))
            else:
                leg_convs.append(SwapFixLegConvention(**kwargs))
        conv_list.append(SwapConvention(name, spot_delay, spot_cal, leg_convs[0], leg_convs[1]))
    return conv_list

# create_query = """CREATE TABLE meeting_dates (
#     bank TEXT, date TEXT, description TEXT,
#     CONSTRAINT meeting_dates_pk PRIMARY KEY (bank, date)
# )"""
# sql.modify(create_query)
# df = pd.read_csv(f'data/meetingdates.csv')
# for _, row in df.iterrows():
#     insert_query = f"""INSERT INTO meeting_dates VALUES (
#     '{row['Central Bank']}',
#     '{dtm.datetime.strptime(row['Date'], '%m/%d/%Y').strftime(DATE_FORMAT)}',
#     '{row['Target Rate']}'
# )"""
#     sql.modify(insert_query)

# create_query = f"""CREATE TABLE {SWAP_CONV_TABLE} (
#     name TEXT, spot_delay TEXT, spot_calendar TEXT, leg_id INTEGER, leg_type TEXT, currency TEXT,
#     coupon_frequency TEXT, day_count_type TEXT, coupon_adjust_type TEXT, coupon_pay_delay TEXT,
#     fixing TEXT, fixing_type TEXT, fixing_lag TEXT, reset_frequency TEXT,
#     CONSTRAINT {SWAP_CONV_TABLE}_pk PRIMARY KEY (name, leg_id)
# )"""
# sql.modify(create_query)
# df = pd.read_csv(f'data/swap_convention.csv')
# for _, row in df.iterrows():
#     insert_query = f"""INSERT INTO {SWAP_CONV_TABLE} VALUES (
#     '{row['Name']}', '{row['SpotDelay']}', '{row['SpotCalendar']}', '{row['LegId']}', '{row['Type']}', '{row['Currency']}',
#     '{row['CouponFrequency']}', '{row['DayCountType']}', '{row['CouponAdjustType']}', '{row['CouponPayDelay']}',
#     '{row['Fixing']}', '{row['FixingType']}', '{row['FixingLag']}', '{row['ResetFrequency']}'
# )"""
