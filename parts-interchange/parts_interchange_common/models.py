from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# Association tables (no ORM class needed — pure join tables)

part_images = Table(
    "part_images", Base.metadata,
    Column("part_id",         Integer, ForeignKey("part.id"),  primary_key=True),
    Column("image_id",        Integer, ForeignKey("image.id"), primary_key=True),
    Column("part_image_text", String(500)),
)

diagram_parts = Table(
    "diagram_parts", Base.metadata,
    Column("diagram_id", Integer, ForeignKey("diagram.id"), primary_key=True),
    Column("part_id",    Integer, ForeignKey("part.id"),    primary_key=True),
    Column("part_index", String(25)),
)

car_parts = Table(
    "car_parts", Base.metadata,
    Column("car_id",  Integer, ForeignKey("car.id"),  primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
)

car_diagrams = Table(
    "car_diagrams", Base.metadata,
    Column("car_id",     Integer, ForeignKey("car.id"),     primary_key=True),
    Column("diagram_id", Integer, ForeignKey("diagram.id"), primary_key=True),
)


class Manufacturer(Base):
    __tablename__ = "manufacturer"
    __table_args__ = (UniqueConstraint("name", name="uq_manufacturer_name"),)

    id      = Column(Integer,     primary_key=True, autoincrement=True)
    name    = Column(String(300), nullable=False)
    base_url = Column(String(300))

    cars   = relationship("Car",   back_populates="manufacturer")
    parts  = relationship("Part",  back_populates="manufacturer")
    images = relationship("Image", back_populates="manufacturer")


class Year(Base):
    __tablename__ = "year"
    __table_args__ = (UniqueConstraint("name", name="uq_year_name"),)

    id   = Column(Integer,     primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)

    cars = relationship("Car", back_populates="year")


class Make(Base):
    __tablename__ = "make"
    __table_args__ = (UniqueConstraint("name", name="uq_make_name"),)

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    name         = Column(String(120), nullable=False)
    select_value = Column(String(120))
    start_year   = Column(Integer)
    end_year     = Column(Integer)

    models = relationship("Model", back_populates="make")
    cars   = relationship("Car",   back_populates="make")


class Model(Base):
    __tablename__ = "model"

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    name         = Column(String(120), nullable=False)
    select_value = Column(String(120))
    make_id      = Column(Integer,     ForeignKey("make.id"), index=True)

    make = relationship("Make", back_populates="models")
    cars = relationship("Car",  back_populates="model")


class Trim(Base):
    __tablename__ = "trim"
    __table_args__ = (UniqueConstraint("name", name="uq_trim_name"),)

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    name         = Column(String(120), nullable=False)
    select_value = Column(String(120))

    cars = relationship("Car", back_populates="trim")


class Engine(Base):
    __tablename__ = "engine"
    __table_args__ = (UniqueConstraint("name", name="uq_engine_name"),)

    id           = Column(Integer,     primary_key=True, autoincrement=True)
    name         = Column(String(120), nullable=False)
    select_value = Column(String(120))

    cars = relationship("Car", back_populates="engine")


class Category(Base):
    __tablename__ = "category"
    __table_args__ = (UniqueConstraint("name", name="uq_category_name"),)

    id   = Column(Integer,     primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)

    subcategories = relationship("Subcategory", back_populates="category")
    diagrams      = relationship("Diagram",     back_populates="category")
    parts         = relationship("Part",        back_populates="category")


class Subcategory(Base):
    __tablename__ = "subcategory"

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    name        = Column(String(120), nullable=False)
    category_id = Column(Integer,     ForeignKey("category.id"), index=True)

    category = relationship("Category", back_populates="subcategories")
    diagrams = relationship("Diagram",  back_populates="subcategory")


class Image(Base):
    __tablename__ = "image"

    id               = Column(Integer,     primary_key=True, autoincrement=True)
    name             = Column(String(100), index=True)
    bucket_path      = Column(String(120))
    url              = Column(String(500))
    alt_text         = Column(String(500))
    saved            = Column(Boolean,     default=False)
    uploaded         = Column(Boolean,     default=False)
    manufacturer_id  = Column(Integer,     ForeignKey("manufacturer.id"), index=True)
    imgcache_hash    = Column(String(64))
    imgcache_bucket  = Column(String(100))

    manufacturer = relationship("Manufacturer", back_populates="images")
    diagrams     = relationship("Diagram",      back_populates="image")


class Part(Base):
    __tablename__ = "part"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    url             = Column(String(500))
    part_number     = Column(String(200), index=True)
    manufacturer_id = Column(Integer,     ForeignKey("manufacturer.id"), index=True)
    title           = Column(String(200))
    category_id     = Column(Integer,     ForeignKey("category.id"))
    other_names     = Column(Text)
    description     = Column(Text)
    replaces        = Column(Text)
    positions       = Column(Text)
    notes           = Column(Text)
    msrp            = Column(Float)
    applications    = Column(Text)
    hazmat          = Column(Boolean)

    manufacturer = relationship("Manufacturer", back_populates="parts")
    category     = relationship("Category",     back_populates="parts")
    cars         = relationship("Car",          secondary=car_parts,     back_populates="parts")
    diagrams     = relationship("Diagram",      secondary=diagram_parts, back_populates="parts")
    images       = relationship("Image",        secondary=part_images)


class Car(Base):
    __tablename__ = "car"

    id              = Column(Integer,      primary_key=True, autoincrement=True)
    year_id         = Column(Integer,      ForeignKey("year.id"),         index=True)
    make_id         = Column(Integer,      ForeignKey("make.id"),         index=True)
    model_id        = Column(Integer,      ForeignKey("model.id"),        index=True)
    trim_id         = Column(Integer,      ForeignKey("trim.id"))
    engine_id       = Column(Integer,      ForeignKey("engine.id"))
    manufacturer_id = Column(Integer,      ForeignKey("manufacturer.id"), index=True)
    car_id          = Column(String(200))
    vehicle_id      = Column(String(200))
    base_url        = Column(String(1000))

    year         = relationship("Year",         back_populates="cars")
    make         = relationship("Make",         back_populates="cars")
    model        = relationship("Model",        back_populates="cars")
    trim         = relationship("Trim",         back_populates="cars")
    engine       = relationship("Engine",       back_populates="cars")
    manufacturer = relationship("Manufacturer", back_populates="cars")
    parts        = relationship("Part",         secondary=car_parts,     back_populates="cars")
    diagrams     = relationship("Diagram",      secondary=car_diagrams,  back_populates="cars")


class Diagram(Base):
    __tablename__ = "diagram"

    id              = Column(Integer,      primary_key=True, autoincrement=True)
    image_id        = Column(Integer,      ForeignKey("image.id"))
    category_id     = Column(Integer,      ForeignKey("category.id"),     index=True)
    sub_category_id = Column(Integer,      ForeignKey("subcategory.id"),  index=True)
    base_car_url    = Column(String(1000))
    category_url    = Column(String(1000))

    image      = relationship("Image",       back_populates="diagrams")
    category   = relationship("Category",    back_populates="diagrams")
    subcategory = relationship("Subcategory", back_populates="diagrams")
    parts      = relationship("Part",        secondary=diagram_parts, back_populates="diagrams")
    cars       = relationship("Car",         secondary=car_diagrams,  back_populates="diagrams")


class Feedback(Base):
    __tablename__ = "feedback"

    id       = Column(Integer,      primary_key=True, autoincrement=True)
    name     = Column(String(250))
    email    = Column(String(250))
    comments = Column(String(2000))


class ScrapeRun(Base):
    __tablename__ = "scrape_run"

    id             = Column(Integer,      primary_key=True, autoincrement=True)
    manufacturer   = Column(String(100),  nullable=False)
    started_at     = Column(DateTime,     nullable=False)
    completed_at   = Column(DateTime)
    cars_processed = Column(Integer,      default=0)
    new_parts      = Column(Integer,      default=0)
    updated_parts  = Column(Integer,      default=0)
    success        = Column(Boolean,      nullable=False, default=False)
    error_message  = Column(String(1000))
