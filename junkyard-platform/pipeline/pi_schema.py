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

pi_trim_table = Table(
    "trim", pi_metadata,
    Column("id",   Integer, primary_key=True),
    Column("name", String(120), nullable=False),
)

pi_engine_table = Table(
    "engine", pi_metadata,
    Column("id",   Integer, primary_key=True),
    Column("name", String(120), nullable=False),  # e.g. "2.4L L4 - Gas"
)

pi_car_table = Table(
    "car", pi_metadata,
    Column("id",        Integer, primary_key=True),
    Column("year_id",   Integer, ForeignKey("year.id")),
    Column("make_id",   Integer, ForeignKey("make.id")),
    Column("model_id",  Integer, ForeignKey("model.id")),
    Column("trim_id",   Integer, ForeignKey("trim.id")),
    Column("engine_id", Integer, ForeignKey("engine.id")),
)
