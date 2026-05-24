# api-v2/src/models/parts.py
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from src.database import Base


class Manufacturer(Base):
    __tablename__ = "manufacturer"
    id = Column(Integer, primary_key=True)
    name = Column(String(300), index=True, unique=True)
    base_url = Column(String(300))


class Category(Base):
    __tablename__ = "category"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    sub_categories = relationship("SubCategory", back_populates="category", lazy="selectin")


class SubCategory(Base):
    __tablename__ = "subcategory"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True)
    category_id = Column(Integer, ForeignKey("category.id"))
    category = relationship("Category", back_populates="sub_categories")


class Image(Base):
    __tablename__ = "image"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), index=True)
    bucket_path = Column(String(120))
    url = Column(String(500))
    alt_text = Column(String(500))
    saved = Column(Boolean, default=False)
    uploaded = Column(Boolean, default=False)
    manufacturer_id = Column(Integer, ForeignKey("manufacturer.id"))


class PartImages(Base):
    __tablename__ = "part_images"
    part_id = Column(Integer, ForeignKey("part.id"), primary_key=True)
    image_id = Column(Integer, ForeignKey("image.id"), primary_key=True)
    part_image_text = Column(String(500))
    image = relationship("Image")


class DiagramParts(Base):
    __tablename__ = "diagram_parts"
    diagram_id = Column(Integer, ForeignKey("diagram.id"), primary_key=True)
    part_id = Column(Integer, ForeignKey("part.id"), primary_key=True)
    part_index = Column(String(25))


class Diagram(Base):
    __tablename__ = "diagram"
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey("image.id"))
    category_id = Column(Integer, ForeignKey("category.id"))
    sub_category_id = Column(Integer, ForeignKey("subcategory.id"))
    base_car_url = Column(String(1000))
    category_url = Column(String(1000))


class Part(Base):
    __tablename__ = "part"
    id = Column(Integer, primary_key=True)
    url = Column(String(500))
    part_number = Column(String(200), index=True)
    manufacturer_id = Column(Integer, ForeignKey("manufacturer.id"))
    title = Column(String(200))
    category_id = Column(Integer, ForeignKey("category.id"))
    other_names = Column(Text)
    description = Column(Text)
    positions = Column(ARRAY(String))
    msrp = Column(Float)
    applications = Column(Text)
    hazmat = Column(Boolean)
    images = relationship("PartImages", lazy="selectin")


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    name = Column(String(250))
    email = Column(String(250))
    comments = Column(String(2000))
