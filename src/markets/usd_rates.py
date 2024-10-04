import datetime as dtm
import logging

from common.chrono.tenor import Tenor
from data_api import cme_client, db_reader
from instruments.rate_curve_instrument import CurveInstrument, Deposit
from instruments.swap import SwapTemplate
from instruments.vol_curve import VolCurve
from markets import usd_lib
from models.rate_curve_builder import RateCurveModel, RateCurveGroupModel
from models.config_context import ConfigContext
from models.data_context import DataContext

logger = logging.Logger(__name__)


CONFIG_CONTEXT: ConfigContext = None


def get_futures_for_curve(value_date: dtm.date, fixing_code: str) -> list[CurveInstrument]:
    codes = db_reader.read_future_codes(fixing_code)
    instruments_crv = []
    for code in codes:
        instruments = CONFIG_CONTEXT.get_futures(code)
        settle_data = cme_client.get_future_settle_prices(code, value_date)
        # Skip futures on expiry date, we only use fixing rates till T
        instruments_active = [ins for ins in instruments if ins.expiry > value_date]
        for ins in instruments_active:
            price = settle_data.get(ins.name)
            if price:
                logger.info(f"Setting price for future {ins.name} to {price}")
                ins.data[value_date] = price
                instruments_crv.append(CurveInstrument(ins))
            else:
                logger.info(f"No price found for future {ins.name}. Skipping")
    instruments_crv.sort()
    return instruments_crv

def get_swaps_curve(val_date: dtm.date, code: str, cutoff: dtm.date = None) -> list[CurveInstrument]:
    swap_prices = cme_client.get_swap_data(code, val_date)
    swap_instruments = []
    for tenor, rate in swap_prices.items():
        ins = SwapTemplate(code, Tenor(tenor), name=f'{code}_{tenor}').to_trade(val_date)
        ins.set_data(val_date, rate)
        curve_ins = CurveInstrument(ins)
        if cutoff and ins.end_date <= cutoff:
            curve_ins.exclude_fit = True
        swap_instruments.append(curve_ins)
    swap_instruments.sort()
    return swap_instruments

def set_step_knots(fut_instruments: list[CurveInstrument], step_dates: list[dtm.date]) -> dtm.date:
    mdt_i = 0
    for ins in fut_instruments:
        if ins.underlier.expiry > step_dates[mdt_i] and not ins.exclude_fit:
            mdt_i += 1
            if mdt_i >= len(step_dates):
                logger.info('Step dates end.')
                break
            if ins.underlier.expiry > step_dates[mdt_i]:
                logger.warning(f"{ins.name} Expiry does not fall between step dates")
                break
        last_knot = step_dates[mdt_i]
        ins.set_knot(last_knot)
    logger.warning(f'Setting step cutoff {last_knot}')
    return last_knot

def _init():
    global CONFIG_CONTEXT, DATA_CONTEXT
    CONFIG_CONTEXT = ConfigContext()
    for code in ['SR3']:
        CONFIG_CONTEXT.add_futures(code, db_reader.read_IMM_futures(code))
    for code in ['SR1', 'FF']:
        CONFIG_CONTEXT.add_futures(code, db_reader.read_serial_futures(code))
    effective_t = Tenor.bday(1, usd_lib.CALENDAR)
    meeting_dates_eff = [effective_t.get_date(dt) for dt in db_reader.read_meeting_dates('FED')]
    CONFIG_CONTEXT.add_meeting_nodes('FED', meeting_dates_eff)
    
    for row in db_reader.read_swap_conventions():
        CONFIG_CONTEXT.add_swap_convention(row)
    
    DATA_CONTEXT = DataContext()
    first_date = Tenor('-3m').get_date(dtm.date.today())
    for code in ['SOFR', 'EFFR']:
        DATA_CONTEXT.add_fixing_series(code, db_reader.read_fixings(code, from_date=first_date))


def construct(val_dt: dtm.date = None):
    last_val_date = usd_lib.get_last_valuation_date()
    if not CONFIG_CONTEXT:
        _init()
        last_fixing_date = DATA_CONTEXT.get_fixing_series('SOFR').data.get_last_point()[0]
        if last_val_date > last_fixing_date:
            logger.error(f"{last_val_date} is after the last available fixing {last_fixing_date}")
    if not val_dt:
        val_dt = last_val_date
    live = val_dt > last_val_date
    
    meeting_dates_eff = [dt for dt in CONFIG_CONTEXT.get_meeting_nodes('FED') if dt > val_dt]

    # SOFR - OIS
    fixing_name = 'SOFR'
    futs_crv = get_futures_for_curve(val_dt, fixing_code=fixing_name)
    fut_cutoff = '5y' if live else '30m'
    fut_cutoff_date = Tenor(fut_cutoff).get_date(val_dt)
    for fi in futs_crv:
        if fi.underlier.expiry > fut_cutoff_date:
            fi.exclude_fit = True
    mdt_sc = set_step_knots(futs_crv, meeting_dates_eff)
    curve_instruments = futs_crv
    if futs_crv[0].knot > meeting_dates_eff[0]:
        deposit = Deposit(meeting_dates_eff[0], name=fixing_name)
        deposit.data[val_dt] = DataContext().get_fixing_series(fixing_name).get(val_dt)
        curve_instruments = [CurveInstrument(deposit)] + futs_crv

    usd_rate_vol = 1.4/100
    rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name=f'{fixing_name}-Vol')
    if not live:
        swaps = get_swaps_curve(val_dt, 'USD_SOFR', cutoff=fut_cutoff_date)
        curve_instruments.extend(swaps)
    curve_defs = [RateCurveModel(curve_instruments,
                    _interpolation_methods = [(mdt_sc, 'LogLinear'), (None, 'LogCubic')],
                    _rate_vol_curve=rate_vol_curve, name=fixing_name)]

    # Fed fund
    fixing_name = 'EFFR'
    ff_futs_crv = get_futures_for_curve(val_dt, fixing_code=fixing_name)
    ff_fut_cutoff = Tenor('13m').get_date(val_dt)
    for fi in ff_futs_crv:
        if fi.underlier.expiry > ff_fut_cutoff:
            fi.exclude_fit = True
    ff_mdt_sc = set_step_knots(ff_futs_crv, meeting_dates_eff)
    ff_curve_instruments = ff_futs_crv
    if ff_futs_crv[0].knot > meeting_dates_eff[0]:
        ff_deposit = Deposit(meeting_dates_eff[0], name=fixing_name)
        ff_deposit.data[val_dt] = DataContext().get_fixing_series(fixing_name).get(val_dt)
        ff_curve_instruments = [CurveInstrument(ff_deposit)] + ff_futs_crv
    
    ff_rate_vol_curve = VolCurve(val_dt, [(val_dt, usd_rate_vol)], name=f'{fixing_name}-Vol')
    if not live:
        ff_swaps = get_swaps_curve(val_dt, code='USD_FF_SOFR', cutoff=ff_fut_cutoff)
        ff_curve_instruments.extend(ff_swaps)
        ff_interps = [(ff_mdt_sc, 'LogLinear'), (None, 'LogCubic')]
    else:
        ff_interps = [(None, 'LogLinear')]
    ff_curve_defs = [RateCurveModel(ff_curve_instruments,
                    _interpolation_methods=ff_interps,
                    _rate_vol_curve=ff_rate_vol_curve,
                    _collateral_curve_id='USD-SOFR', _spread_from='USD-SOFR', name=fixing_name)]
    
    return [
        RateCurveGroupModel(val_dt, curve_defs, _calendar=usd_lib.CALENDAR, name='USD'),
        RateCurveGroupModel(val_dt, ff_curve_defs, _calendar=usd_lib.CALENDAR, name='USD'),
    ]

