import os
from urllib.parse import quote_plus


def get_psycopg2_params() -> dict:
    return {
        'user':   os.getenv('db_user', 'scrapestack'),
        'password': os.getenv('db_pass', ''),
        'host':   os.getenv('db_host', 'localhost'),
        'port':   int(os.getenv('db_port', '5433')),
        'dbname': os.getenv('db_name', 'parts_interchange'),
    }


def get_db_url() -> str:
    p = get_psycopg2_params()
    return (
        f"postgresql://{p['user']}:{quote_plus(p['password'])}"
        f"@{p['host']}:{p['port']}/{p['dbname']}"
    )
