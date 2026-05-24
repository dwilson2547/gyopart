from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text

from src.db import Base

car_parts = Table(
    "car_parts",
    Base.metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
)


class Year(Base):
    __tablename__ = "year"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Make(Base):
    __tablename__ = "make"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Model(Base):
    __tablename__ = "model"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    make_id = Column(Integer, ForeignKey("make.id"), nullable=False)


class Trim(Base):
    __tablename__ = "trim"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Engine(Base):
    __tablename__ = "engine"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Car(Base):
    __tablename__ = "car"
    id = Column(Integer, primary_key=True)
    year_id = Column(Integer, ForeignKey("year.id"), nullable=False)
    make_id = Column(Integer, ForeignKey("make.id"), nullable=False)
    model_id = Column(Integer, ForeignKey("model.id"), nullable=False)
    trim_id = Column(Integer, ForeignKey("trim.id"), nullable=False)
    engine_id = Column(Integer, ForeignKey("engine.id"), nullable=False)


class Part(Base):
    __tablename__ = "part"
    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    part_number = Column(String(200))
    description = Column(Text)
    other_names = Column(String)
