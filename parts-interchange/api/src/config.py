from urllib.parse import quote_plus
import os

db_host = os.getenv('db_url', 'localhost:5432')
db_user = os.getenv('POSTGRES_USER', 'parts_user')
db_pass = os.getenv('POSTGRES_PASSWORD', 'parts_pass')
db_name = os.getenv('POSTGRES_DB', 'parts_interchange')

class Config:
    SQLALCHEMY_DATABASE_URI='postgresql+psycopg2://%s:%s@%s/%s' % (db_user.strip(), quote_plus(db_pass.strip()), db_host.strip(), db_name.strip())
    debug=True