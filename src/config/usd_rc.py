
import datetime as dtm
import logging

from common.chrono.tenor import Tenor
from instruments.rate_future import RateFutureC
from instruments.rate_curve_instrument import Deposit
from instruments.swap import SwapTemplate, SwapTrade
from instruments.vol_curve import VolCurve
from config import usd_mkt
import data_api.reader as data_reader
import data_api.cme as cme_api
from models.rate_curve_builder import RateCurveModel, RateCurveGroupModel
from models.context import ConfigContext
from models.data_context import DataContext

logger = logging.Logger(__name__)


CONFIG_CONTEXT: ConfigContext = None


def get_futures_for_curve(value_date: dtm.date, fixing_code: str) -> list[RateFutureC]:
    codes = data_reader.read_future_codes(fixing_code)
    instruments_crv = []
    for code in codes:
        instruments = CONFIG_CONTEXT.get_futures(code)
        settle_data = cme_api.get_fut_settle_prices(code, value_date)
        instruments_active = [ins for ins in instruments if ins.expiry > value_date]
        for ins in instruments_active:
            price = settle_data.get(ins.name)
            if price:
                logger.info(f"Setting price for future {ins.name} to {price}")
                ins.data[value_date] = price
                instruments_crv.append(ins)
            else:
                logger.info(f"No price found for future {ins.name}. Skipping")
    instruments_crv.sort()
    return instruments_crv

def get_swaps_curve(val_date: dtm.date, code: str, cutoff: dtm.date = None) -> list[SwapTrade]:
    swap_prices = cme_api.get_swap_data(code, val_date)
    swap_instruments = []
    for tenor, rate in swap_prices.items():
        ins = SwapTemplate(code, Tenor(tenor), name=f'{code}_{tenor}').to_trade(val_date)
        ins.set_data(val_date, rate)
        if cutoff and ins.end_date <= cutoff:
            ins.exclude_knot = True
        swap_instruments.append(ins)
    swap_instruments.sort()
    return swap_instruments

def get_meeting_dates(val_date: dtm.date, effective_t = Tenor('1B')) -> list[dtm.date]:
    meeting_dates = data_reader.read_meeting_dates('FED')
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
    global CONFIG_CONTEXT, DATA_CONTEXT
    CONFIG_CONTEXT = ConfigContext()
    for code in ['SR3']:
        CONFIG_CONTEXT.add_futures(code, data_reader.read_IMM_futures(code))
    for code in ['SR1', 'FF']:
        CONFIG_CONTEXT.add_futures(code, data_reader.read_serial_futures(code))
    
    for row in data_reader.read_swap_conventions():
        CONFIG_CONTEXT.add_swap_convention(row)
    
    DATA_CONTEXT = DataContext()
    first_date = Tenor('-3m').get_date(dtm.date.today())
    for code in ['SOFR', 'EFFR']:
        DATA_CONTEXT.add_fixing_curve(data_reader.read_fixings(code, from_date=first_date))


def construct(val_dt: dtm.date = None):
    last_val_date = usd_mkt.get_last_valuation_date()
    if not CONFIG_CONTEXT:
        _init()
    if not val_dt:
        val_dt = last_val_date
    live = val_dt > last_val_date
    
    next_btenor = Tenor.bday(1, usd_mkt.CALENDAR)
    meeting_dates_eff = get_meeting_dates(val_dt, effective_t=next_btenor)

    # SOFR - OIS
    fixing_name = 'SOFR'
    deposit = Deposit(next_btenor.get_date(val_dt), name=fixing_name)  # meeting_dates_eff[0])
    deposit.data[val_dt] = DataContext().get_fixings(fixing_name).get_last_value()

    futs_crv = get_futures_for_curve(val_dt, fixing_code=fixing_name)
    fut_cutoff = '5y' if live else '30m'
    fut_cutoff_date = Tenor(fut_cutoff).get_date(val_dt)
    # Skip futures on expiry date, we only use fixing rates till T
    for fi in futs_crv:
        if deposit.end > fi.expiry or fi.expiry > fut_cutoff_date:
            fi.exclude_knot = True
    mdt_sc = set_step_knots(futs_crv, meeting_dates_eff)

    usd_rate_vol = 1.4/100
    rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name=f'{fixing_name}-Vol')
    if live:
        curve_instruments = [deposit] + futs_crv
    else:
        swaps = get_swaps_curve(val_dt, 'USD_SOFR', cutoff=fut_cutoff_date)
        curve_instruments = [deposit] + futs_crv + swaps
    curve_defs = [RateCurveModel(curve_instruments,
                    _interpolation_methods = [(mdt_sc, 'LogLinear'), (None, 'LogCubic')],
                    _rate_vol_curve=rate_vol_curve, name=fixing_name)]

    # Fed fund
    fixing_name = 'EFFR'
    ff_deposit = Deposit(next_btenor.get_date(val_dt), name=fixing_name)
    ff_deposit.data[val_dt] = DataContext().get_fixings(fixing_name).get_last_value()

    ff_futs_crv = get_futures_for_curve(val_dt, fixing_code=fixing_name)
    ff_fut_cutoff = Tenor('13m').get_date(val_dt)
    for fi in ff_futs_crv:
        if ff_deposit.end > fi.expiry or fi.expiry > ff_fut_cutoff:
            fi.exclude_knot = True
    ff_mdt_sc = set_step_knots(ff_futs_crv, meeting_dates_eff)
    
    ff_rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name=f'{fixing_name}-Vol')
    if live:
        ff_curve_instruments = [ff_deposit] + ff_futs_crv
        interps = [(None, 'LogLinear')]
    else:
        ff_swaps = get_swaps_curve(val_dt, code='USD_FF_SOFR', cutoff=ff_fut_cutoff)
        ff_curve_instruments = [ff_deposit] + ff_futs_crv + ff_swaps
        interps = [(ff_mdt_sc, 'LogLinear'), (None, 'LogCubic')]
    ff_curve_defs = [RateCurveModel(ff_curve_instruments,
                    _interpolation_methods=interps, _rate_vol_curve=ff_rate_vol_curve,
                    _collateral_curve='USD-SOFR', _spread_from='USD-SOFR', name='FF')]
    
    return [
        RateCurveGroupModel(val_dt, curve_defs, _calendar=usd_mkt.CALENDAR, name='USD'),
        RateCurveGroupModel(val_dt, ff_curve_defs, _calendar=usd_mkt.CALENDAR, name='USD'),
    ]

