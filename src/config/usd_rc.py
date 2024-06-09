
import datetime as dtm
import logging
from copy import deepcopy

import common.chrono as date_lib
from instruments.fixing import add_fixing_curve
from instruments.swap_convention import add_swap_convention
from instruments.rate_curve_instrument import Deposit
from instruments.swap import DomesticSwap, BasisSwap
from instruments.vol_curve import VolCurve
import data_api.parser as data_parser
import data_api.cme as cme_api
from models.rate_curve_builder import RateCurveModel, RateCurveGroupModel

logger = logging.Logger(__name__)


FIXING_SWAP_MAP = {
    'SOFR':     ('USD_SOFR', DomesticSwap),
    'SOFR_FF':  ('USD_FF_SOFR', BasisSwap),
}
CALENDAR = date_lib.Calendar.USEX

_SOFR_RATES = None
_FF_RATES = None
_SOFR_IMM_CONTRACTS = None
_SOFR_SERIAL_CONTRACTS = None
_FF_SERIAL_CONTRACTS = None
_INITIALIZED = False


def get_valuation_dates(from_date: dtm.date, to_date: dtm.date = None):
    if not from_date:
        if not to_date:
            return [None]
        else:
            return [to_date]
    if not to_date:
        to_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=CALENDAR.value)
    return date_lib.get_bdate_series(from_date, to_date, CALENDAR)

def get_futures_for_curve(fut_instruments: list, val_date: dtm.date, contract_type: str) -> list:
    fut_instruments_crv = []
    # futures_prices = data_cme.load_prices_ftp(contract_type)
    # assert futures_prices[0] == val_date, "Valuation date and market data mismatch"
    # for ins in fut_instruments:
    #     f_code = ins.name[:-3]
    #     m_code = ins.name[-3:]
    #     if f_code in futures_prices[1] and m_code in futures_prices[1][f_code]:
    #         price = futures_prices[1][f_code][m_code]
    futures_prices = {}
    if contract_type == 'SOFR':
        codes = ['SR1', 'SR3']
    elif contract_type == 'FF':
        codes = ['FF']
    for code in codes:
        fut_settle_data = cme_api.load_fut_settle_prices(code, val_date)
        futures_prices.update(fut_settle_data[1])
    for ins in fut_instruments:
        if ins.name in futures_prices:
            price = futures_prices[ins.name]
            logger.info(f"Setting price for future {ins.name} to {price}")
            ins_c = deepcopy(ins)
            ins_c.set_market(val_date, price)
            fut_instruments_crv.append(ins_c)
        else:
            logger.info(f"No price found for future {ins.name}. Skipping")
    return fut_instruments_crv

def get_swaps_curve(val_date: dtm.date, fixing_type: str = 'SOFR', cutoff: dtm.date = None) -> list[DomesticSwap]:
    swap_prices = cme_api.load_swap_data(fixing_type)
    assert val_date in swap_prices, f"Swap prices missing for {val_date}"
    swap_convention, swap_obj = FIXING_SWAP_MAP[fixing_type]
    swap_instruments = []
    for tenor, rate in swap_prices[val_date].items():
        ins = swap_obj(_convention_name=swap_convention, _end=date_lib.Tenor(tenor), name=f'{swap_convention}_{tenor}')
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
        if ins.expiry > step_dates[mdt_i] and not ins.exclude_knot:
            mdt_i += 1
            if mdt_i >= len(step_dates):
                logger.info('Step dates end.')
                break
            if ins.expiry > step_dates[mdt_i]:
                logger.warning(f"{ins.name} Expiry does not fall between step dates")
                break
        ins.knot = last_knot = step_dates[mdt_i]
    logger.warning(f'Setting step cutoff {last_knot}')
    return last_knot

def _init():
    global _SOFR_RATES, _FF_RATES, _SOFR_IMM_CONTRACTS, _SOFR_SERIAL_CONTRACTS, _FF_SERIAL_CONTRACTS, _INITIALIZED
    _SOFR_RATES = data_parser.read_fixings(filename='SOFR.csv', date_col='Effective Date', rate_col='Rate (%)')
    _FF_RATES = data_parser.read_fixings(filename='EFFR.csv', date_col='Effective Date', rate_col='Rate (%)')
    _SOFR_IMM_CONTRACTS = data_parser.read_IMM_futures(filename='SR3.csv', underlying='SOFR')
    _SOFR_SERIAL_CONTRACTS = data_parser.read_serial_futures(filename='SR1.csv', underlying='SOFR')
    _FF_SERIAL_CONTRACTS = data_parser.read_serial_futures(filename='FF.csv', underlying='EFFR')
    
    for fc in [_SOFR_RATES, _FF_RATES]:
        add_fixing_curve(fc)
    
    for k, v in data_parser.read_swap_conventions().items():
        add_swap_convention(*k, v)

    _INITIALIZED = True


def construct(val_dt: dtm.date = None):
    last_val_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=CALENDAR.value)
    if not val_dt or not _INITIALIZED:
        _init()
        val_dt = last_val_date
    live = val_dt > last_val_date
    
    next_btenor = date_lib.Tenor.bday(1, CALENDAR)
    meeting_dates_eff = get_meeting_dates(val_dt, effective_t=next_btenor)

    # SOFR - OIS
    deposit = Deposit(next_btenor, name='SOFR')  # meeting_dates_eff[0])
    deposit.set_market(val_dt, _SOFR_RATES.get_last_value())

    fut_cutoff = '5y' if live else '30m'
    fut_cutoff_date = date_lib.Tenor(fut_cutoff).get_date(val_dt)
    fut_instruments = _SOFR_IMM_CONTRACTS + _SOFR_SERIAL_CONTRACTS
    # Skip futures on expiry date, we only use fixing rates till T
    fut_instruments = [fi for fi in fut_instruments if deposit.end_date < fi.expiry]
    for fi in fut_instruments:
        if fi.expiry > fut_cutoff_date:
            fi.exclude_knot = True
        else:
            fi.exclude_knot = False
    fut_instruments.sort()
    futs_crv = get_futures_for_curve(fut_instruments, val_dt, contract_type='SOFR')
    mdt_sc = set_step_knots(futs_crv, meeting_dates_eff)

    usd_rate_vol = 1.4/100
    rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name='SOFR-Vol')
    if live:
        curve_instruments = [deposit] + futs_crv
    else:
        swaps = get_swaps_curve(val_dt, cutoff=fut_cutoff_date)
        curve_instruments = [deposit] + futs_crv + swaps
    curve_defs = [RateCurveModel(curve_instruments,
                                  _interpolation_methods = [(mdt_sc, 'LogLinear'), (None, 'LogCubic')],
                                  _rate_vol_curve=rate_vol_curve,
                                  name='SOFR')]

    # Fed fund
    ff_deposit = Deposit(next_btenor, name='EFFR')
    ff_deposit.set_market(val_dt, _FF_RATES.get_last_value())

    ff_fut_cutoff = date_lib.Tenor('13m').get_date(val_dt)
    ff_futs = [fi for fi in _FF_SERIAL_CONTRACTS if ff_deposit.end_date < fi.expiry]
    for fi in ff_futs:
        if fi.expiry > ff_fut_cutoff:
            fi.exclude_knot = True
    ff_futs_crv = get_futures_for_curve(ff_futs, val_dt, contract_type='FF')
    ff_mdt_sc = set_step_knots(ff_futs_crv, meeting_dates_eff)
    
    ff_rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name='FF-Vol')
    if live:
        ff_curve_instruments = [ff_deposit] + ff_futs_crv
        interps = [(None, 'LogLinear')]
    else:
        ff_swaps = get_swaps_curve(val_dt, fixing_type='SOFR_FF', cutoff=ff_fut_cutoff)
        ff_curve_instruments = [ff_deposit] + ff_futs_crv + ff_swaps
        interps = [(ff_mdt_sc, 'LogLinear'), (None, 'LogCubic')]
    curve_defs.append(RateCurveModel(ff_curve_instruments,
                                      _interpolation_methods=interps,
                                      _rate_vol_curve=ff_rate_vol_curve,
                                      _collateral_curve='USD-SOFR',
                                      _spread_from='USD-SOFR',
                                      name='FF'))
    
    return RateCurveGroupModel(val_dt, curve_defs, _calendar=CALENDAR, name='USD')

