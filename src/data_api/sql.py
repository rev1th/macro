
import sqlite3

DATE_FORMAT = '%Y-%m-%d'

def fetch_query(query: str, filename: str = 'macro_meta.db', count: int = 0):
    connect = sqlite3.connect(f'data/{filename}')
    cursor = connect.cursor()
    try:
        exec_obj = cursor.execute(query)
        if count == 1:
            res = exec_obj.fetchone()
        elif count > 1:
            res = exec_obj.fetchmany(count)
        else:
            res = exec_obj.fetchall()
    except Exception as ex:
        raise RuntimeError(f'Fetch failed: {ex}')
    connect.close()
    return res

def modify_query(query: str, filename: str = 'macro_meta.db') -> bool:
    connect = sqlite3.connect(f'data/{filename}')
    cursor = connect.cursor()
    try:
        cursor.execute(query)
        connect.commit()
    except Exception as ex:
        raise RuntimeError(f'Modify failed: {ex}')
    connect.close()
    return True

