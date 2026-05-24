from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from urllib.parse import quote_plus
from workspace.web_scrapers.junkyard_inventory_scrapers.pull_a_part_scraper.old.models import Base


class DB:

    def get_db_url(self, db_user: str, db_pass: str, db_url: str):
        return 'mysql+pymysql://%s:%s@%s' % (db_user.strip(), quote_plus(db_pass.strip()), db_url.strip())

    def create_session(self):
        db_user = 'test'
        db_pass = 'dw31571102'
        db_url = 'localhost:3306/parts-interchange'

        engine = create_engine(self.get_db_url(db_user, db_pass, db_url))

        Base.metadata.create_all(engine)

        session = Session(engine)
        return session