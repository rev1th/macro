
import datetime as dtm

from common import request_web as request
from data_api import sql

NYFED_URL = 'https://markets.newyorkfed.org/read'
NYFED_URL_DATE_FORMAT = '%Y-%m-%d'
NYFED_URL_CODEMAP = {
    'SOFR': 520,
    'EFFR': 500,
}
NYFED_DATE_FORMAT = '%m/%d/%Y'
NYFED_TABLE = 'rates_fixings'

def update_data(code: str):
    if code not in NYFED_URL_CODEMAP:
        raise Exception(f'{code} not found in URL mapping')
    last_date = get_last_data_date(code) + dtm.timedelta(days=1)
    params = {
        'startDt': last_date.strftime(NYFED_URL_DATE_FORMAT),
        'eventCodes': NYFED_URL_CODEMAP[code],
        'productCode': 50,
        'sort': 'postDt:-1,eventCode:1',
        'format': 'csv',
    }
    content = request.url_get(NYFED_URL, params=params)
    lines = content.strip().split('\n')
    for row in lines[1:]:
        cells = row.split(',')
        date_str, rate_type, rate = [cells[id] for id in [0, 1, 2]]
        date_sql = dtm.datetime.strptime(date_str, NYFED_DATE_FORMAT).date().strftime(sql.DATE_FORMAT)
        insert_query = (f"INSERT INTO {NYFED_TABLE} VALUES ('USD', '{rate_type}', '{date_sql}', '{rate}')")
        sql.modify_query(insert_query)
    return True

def get_last_data_date(code: str) -> dtm.date:
    select_query = f"SELECT date FROM {NYFED_TABLE} WHERE type = '{code}' ORDER BY date DESC"
    data_date = sql.fetch_query(select_query, count=1)
    return dtm.datetime.strptime(data_date[0], sql.DATE_FORMAT).date()

def get_data(code: str, from_date: dtm.date):
    select_query = f"SELECT date, rate FROM {NYFED_TABLE} WHERE type = '{code}' AND date >= '{from_date}' ORDER BY date DESC"
    select_res = sql.fetch_query(select_query)
    res_fmt = [(dtm.datetime.strptime(row[0], sql.DATE_FORMAT).date(), row[1]) for row in select_res]
    return res_fmt

def main():
    for fix in NYFED_URL_CODEMAP:
        update_data(fix)

if __name__ == '__main__':
    main()

# create_query = """CREATE TABLE rates_fixings (
#     currency TEXT, type TEXT, date TEXT, rate REAL,
#     CONSTRAINT rates_fixings_pk PRIMARY KEY (currency, type, date)
# )"""
# sql.modify_query(create_query)
# for file in ['EFFR.csv', 'SOFR.csv']:
#     df = pd.read_csv(f'data/{file}')
#     for _, row in df.iterrows():
#         insert_query = f"""INSERT INTO rates_fixings VALUES (
#     'USD', '{row['Rate Type']}',
#     '{dtm.datetime.strptime(row['Effective Date'], '%m/%d/%Y').strftime(DATE_FORMAT)}',
#     '{row['Rate (%)']}'
# )"""
