# api-v2/src/models/vehicle.py
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship
from src.database import Base

car_categories = Table(
    "car_categories", Base.metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("category_id", Integer, ForeignKey("category.id"), primary_key=True),
)

car_diagrams = Table(
    "car_diagrams", Base.metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("diagram_id", Integer, ForeignKey("diagram.id"), primary_key=True),
)

car_parts = Table(
    "car_parts", Base.metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
)


class Year(Base):
    __tablename__ = "year"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)


class Make(Base):
    __tablename__ = "make"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    select_value = Column(String(120))
    start_year = Column(Integer)
    end_year = Column(Integer)
    models = relationship("Model", back_populates="make", lazy="selectin")


class Model(Base):
    __tablename__ = "model"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True)
    select_value = Column(String(120))
    make_id = Column(Integer, ForeignKey("make.id"))
    make = relationship("Make", back_populates="models")


class Trim(Base):
    __tablename__ = "trim"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    select_value = Column(String(120))


class Engine(Base):
    __tablename__ = "engine"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    select_value = Column(String(120))


class Car(Base):
    __tablename__ = "car"
    id = Column(Integer, primary_key=True)
    year_id = Column(Integer, ForeignKey("year.id"))
    make_id = Column(Integer, ForeignKey("make.id"))
    model_id = Column(Integer, ForeignKey("model.id"))
    trim_id = Column(Integer, ForeignKey("trim.id"))
    engine_id = Column(Integer, ForeignKey("engine.id"))
    manufacturer_id = Column(Integer, ForeignKey("manufacturer.id"))
    car_id = Column(String(200))
    vehicle_id = Column(String(200))
    base_url = Column(String(1000))
    year = relationship("Year", lazy="selectin")
    make = relationship("Make", lazy="selectin")
    model = relationship("Model", lazy="selectin")
    trim = relationship("Trim", lazy="selectin")
    engine = relationship("Engine", lazy="selectin")
