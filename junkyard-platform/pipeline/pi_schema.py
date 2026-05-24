from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

pi_metadata = MetaData()

pi_year_table = Table(
    "year", pi_metadata,
    Column("id",   Integer, primary_key=True),
    Column("name", String(120), nullable=False),
)

pi_make_table = Table(
    "make", pi_metadata,
    Column("id",   Integer, primary_key=True),
    Column("name", String(120), nullable=False),
)

pi_model_table = Table(
    "model", pi_metadata,
    Column("id",      Integer, primary_key=True),
    Column("name",    String(120), nullable=False),
    Column("make_id", Integer, ForeignKey("make.id")),
)

pi_car_table = Table(
    "car", pi_metadata,
    Column("id",       Integer, primary_key=True),
    Column("year_id",  Integer, ForeignKey("year.id")),
    Column("make_id",  Integer, ForeignKey("make.id")),
    Column("model_id", Integer, ForeignKey("model.id")),
)
