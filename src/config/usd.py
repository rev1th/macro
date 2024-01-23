
import datetime as dtm
import logging

import common.chrono as date_lib
from models.base_types import FIXING_CURVE_MAP
from models.swap_convention import SWAP_CONVENTION_MAP
from models.rate_curve_instrument import Deposit
from models.swap import DomesticSwap, BasisSwap
import data_api.parser as data_parser
import data_api.cme as data_cme
from rate_curve_builder import YieldCurveModel, YieldCurveSetModel
from models.vol_curve import VolCurve

logger = logging.Logger(__name__)


def get_futures_for_curve(fut_instruments: list, val_date: dtm.date, contract_type: str) -> list:
    futures_prices = data_cme.load_prices(contract_type)
    assert futures_prices[0] == val_date, "Valuation date and market data mismatch"
    fut_instruments_crv = []
    for ins in fut_instruments:
        f_code = ins.name[:-3]
        m_code = ins.name[-3:]
        if f_code in futures_prices[1] and m_code in futures_prices[1][f_code]:
            logger.info(f"Setting price for future {ins.name} to {futures_prices[1][f_code][m_code]}")
            ins.set_market(val_date, futures_prices[1][f_code][m_code])
            # ins.set_convexity(vol=RATE_VOL)
            fut_instruments_crv.append(ins)
        else:
            logger.warning(f"No price found for future {ins.name}. Skipping")
    return fut_instruments_crv

def get_swaps_curve(val_date: dtm.date, fixing_type: str = 'SOFR', cutoff: dtm.date = None) -> list[DomesticSwap]:
    swap_prices = data_cme.load_swap_data(fixing_type)
    assert val_date in swap_prices, f"Swap prices missing for {val_date}"
    if fixing_type == 'FF':
        swap_index = 'USDFFSOFR'
    elif fixing_type == 'SOFR':
        swap_index = 'USDSOFR'
    swap_instruments = []
    for tenor, rate in swap_prices[val_date].items():
        if fixing_type == 'FF':
            ins = BasisSwap(_index=swap_index, _end=date_lib.Tenor(tenor), name=f'{swap_index}_{tenor}')
            ins.set_market(val_date, rate)
        elif fixing_type == 'SOFR':
            ins = DomesticSwap(_index=swap_index, _end=date_lib.Tenor(tenor), name=f'{swap_index}_{tenor}')
            ins.set_market(val_date, rate)
        if cutoff and ins.end_date <= cutoff:
            ins.exclude_knot = True
        swap_instruments.append(ins)
    return swap_instruments

def get_meeting_dates(val_date: dtm.date, effective_t = date_lib.Tenor('1B')) -> list[dtm.date]:
    meeting_dates = data_parser.read_meeting_dates()
    # meeting_dates.sort()
    meeting_dates_eff = [effective_t.get_date(dt) for dt in meeting_dates if dt >= val_date]
    return meeting_dates_eff

def set_step_knots(fut_instruments: list, step_dates: list[dtm.date]) -> dtm.date:
    if not step_dates:
        return None
    mdt_i = 0
    for ins in fut_instruments:
        if ins.expiry > step_dates[mdt_i]:
            mdt_i += 1
            if mdt_i >= len(step_dates)-1:
                logger.info('Step dates end.')
                break
            if ins.expiry > step_dates[mdt_i]:
                logger.warning(f"{ins.name} Expiry does not fall between step dates")
                break
        ins.knot = last_knot = step_dates[mdt_i]
    logger.warning(f'Setting step cutoff {last_knot}')
    return last_knot


def construct():
    us_cal = 'US-NY'
    val_dt = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=us_cal)

    sofr_rates = data_parser.read_fixings(filename='SOFR.csv', date_col='Effective Date', rate_col='Rate (%)')
    ff_rates = data_parser.read_fixings(filename='EFFR.csv', date_col='Effective Date', rate_col='Rate (%)')
    imms = data_parser.read_IMM_futures(filename='SR3.csv', underlying='SOFR', name_col='productCode', 
                                        expiry_col='lastTrade', settle_col='settlement')
    serials = data_parser.read_serial_futures(filename='SR1.csv', underlying='SOFR', name_col='productCode', 
                                              expiry_col='lastTrade', settle_col='settlement')
    ff_serials = data_parser.read_serial_futures(filename='FF.csv', underlying='EFFR', name_col='productCode',
                                                 expiry_col='lastTrade', settle_col='settlement')
    
    for r in [sofr_rates, ff_rates]:
        FIXING_CURVE_MAP[r.name] = r
    
    for k, v in data_parser.read_swap_conventions().items():
        SWAP_CONVENTION_MAP[k] = v
    
    next_btenor = date_lib.Tenor(('1B', us_cal))
    meeting_dates_eff = get_meeting_dates(val_dt, effective_t=next_btenor)

    # SOFR - OIS
    deposit = Deposit(next_btenor, name='SOFR')  # meeting_dates_eff[0])
    deposit.set_market(val_dt, sofr_rates.get_last_value())

    fut_cutoff = date_lib.Tenor('30m').get_date(val_dt)
    fut_instruments = imms + serials
    # Skip futures on expiry date, we only use fixing rates till T
    fut_instruments = [fi for fi in fut_instruments if deposit.end_date < fi.expiry <= fut_cutoff]
    fut_instruments.sort()
    mdt_sc = set_step_knots(fut_instruments, meeting_dates_eff)

    futs_crv = get_futures_for_curve(fut_instruments, val_dt, contract_type='SOFR')
    usd_rate_vol = 1.4/100
    rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name='OIS-Vol')
    swaps = get_swaps_curve(val_dt, cutoff=fut_cutoff)
    curve_instruments = [deposit] + futs_crv + swaps
    curve_defs = [YieldCurveModel(curve_instruments,
                                       _step_cutoff = mdt_sc,
                                       _rate_vol_curve=rate_vol_curve,
                                       name='OIS')]

    # Fed fund
    ff_deposit = Deposit(next_btenor, name='EFFR')
    ff_deposit.set_market(val_dt, ff_rates.get_last_value())

    ff_fut_cutoff = date_lib.Tenor('13m').get_date(val_dt)
    ff_futs = [fi for fi in ff_serials if ff_deposit.end_date < fi.expiry <= ff_fut_cutoff]
    ff_mdt_sc = set_step_knots(ff_futs, meeting_dates_eff)
    
    ff_futs_crv = get_futures_for_curve(ff_futs, val_dt, contract_type='FF')
    ff_rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name='FF-Vol')
    ff_swaps = get_swaps_curve(val_dt, fixing_type='FF', cutoff=ff_fut_cutoff)
    ff_curve_instruments = [ff_deposit] + ff_futs_crv + ff_swaps
    curve_defs.append(YieldCurveModel(ff_curve_instruments,
                                           _step_cutoff = ff_mdt_sc,
                                           _rate_vol_curve=ff_rate_vol_curve,
                                           name='FF'))
    
    return YieldCurveSetModel(val_dt, curve_defs, _calendar=us_cal, name='USD')

