from urllib.parse import quote_plus
import os

db_url = os.getenv('db_url')
db_user = os.getenv('db_user')
db_pass = os.getenv('db_pass')


class Config:
    # SQLALCHEMY_DATABASE_URI='mysql+pymysql://parts_direct_scraper:%s@192.168.0.5:3606/parts-direct' % quote_plus('299kR@lr&2e53%0vVHHkeA')
    SQLALCHEMY_DATABASE_URI='mysql+pymysql://%s:%s@%s' % (db_user.strip(), quote_plus(db_pass.strip()), db_url.strip())


def get_db_url(db_user: str, db_pass: str, db_url: str):
    return 'mysql+pymysql://%s:%s@%s' % (db_user.strip(), quote_plus(db_pass.strip()), db_url.strip())

