import datetime as dtm

from common import sql
from data_api.db_config import PRICES_DB
from .nyfed_server import NYFED_TABLE, NYFED_URL_CODEMAP, update_fixing

def get_data(code: str, from_date: dtm.date) -> list[tuple[dtm.date, float]]:
    select_query = f"SELECT date, rate FROM {NYFED_TABLE} WHERE type = '{code}' AND date >= '{from_date}' ORDER BY date DESC"
    select_res = sql.fetch(select_query, PRICES_DB)
    res_fmt = [(dtm.datetime.strptime(row[0], sql.DATE_FORMAT).date(), row[1]) for row in select_res]
    return res_fmt

def get(from_date: dtm.date):
    return {code: get_data(code, from_date) for code in NYFED_URL_CODEMAP}

def get_last_fixing_date(code: str) -> dtm.date:
    select_query = f"SELECT date FROM {NYFED_TABLE} WHERE type = '{code}' ORDER BY date DESC"
    data_date = sql.fetch(select_query, PRICES_DB, count=1)
    return dtm.datetime.strptime(data_date[0], sql.DATE_FORMAT).date()

def update():
    for code in NYFED_URL_CODEMAP:
        last_date = get_last_fixing_date(code) + dtm.timedelta(days=1)
        if not update_fixing(code, last_date):
            return False
    return True

if __name__ == '__main__':
    update()
