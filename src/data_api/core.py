
import os

DATA_FOLDER = "data"
DATE_FORMAT = "%m/%d/%Y"

def data_path(filename: str, format: str = None):
    if format:
        filename = f'{filename}.{format}'
    return os.path.join(DATA_FOLDER, filename)
