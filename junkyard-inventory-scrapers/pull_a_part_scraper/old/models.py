from sqlalchemy import Column, Integer, String, DateTime, Table, ForeignKey, Boolean, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

DecBase = declarative_base()

class Base(DecBase):
    __abstract__ = True
    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

car_categories = Table('car_categories', Base.metadata,
    Column('car_id', Integer, ForeignKey('car.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('category.id'), primary_key=True))

car_diagrams = Table('car_diagrams', Base.metadata,
    Column('car_id', Integer, ForeignKey('car.id'), primary_key=True),
    Column('diagram_id', Integer, ForeignKey('diagram.id'), primary_key=True))

car_parts = Table('car_parts', Base.metadata,
    Column('car_id', Integer, ForeignKey('car.id'), primary_key=True),
    Column('part_id', Integer, ForeignKey('part.id'), primary_key=True))

class PartImages(Base):
    __tablename__ = 'part_images'

    # id = Column(Integer, primary_key=True)
    # part_id = Column(Integer, ForeignKey('part.id'))
    # main_id = Column(Integer, ForeignKey('image.id'))
    # preview_id = Column(Integer, ForeignKey('image.id'))
    # thumb_id = Column(Integer, ForeignKey('image.id'))

    part_id = Column(Integer, ForeignKey('part.id'), primary_key=True)
    image_id = Column(Integer, ForeignKey('image.id'), primary_key=True)
    
    part_image_text = Column(String(500))
    image = relationship('Image', back_populates='parts')
    part = relationship('Part', back_populates='images')

class DiagramParts(Base):
    __tablename__ = 'diagram_parts'
    diagram_id = Column(Integer, ForeignKey('diagram.id'), primary_key=True)
    part_id = Column(Integer, ForeignKey('part.id'), primary_key=True)
    part_index = Column(String(50))
    part = relationship('Part', back_populates='diagrams')
    diagram = relationship('Diagram', back_populates='parts')

class Category(Base):
    __tablename__ = 'category'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)

class SubCategory(Base):
    __tablename__ = 'subcategory'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True)
    category_id = Column(Integer, ForeignKey('category.id'))
    category = relationship('Category', backref='sub_categories')

class Diagram(Base):
    __tablename__ = 'diagram'
    id = Column(Integer(), primary_key=True)
    image_id = Column(Integer, ForeignKey('image.id'))
    category_id = Column(Integer, ForeignKey('category.id'))
    sub_category_id = Column(Integer, ForeignKey('subcategory.id'))
    base_car_url = Column(String(1000))
    category_url = Column(String(1000))
    image = relationship('Image')
    parts = relationship('DiagramParts', back_populates='diagram')
    category = relationship('Category')
    sub_category = relationship('SubCategory')

class Image(Base):
    __tablename__ = 'image'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), index=True)
    bucket_path = Column(String(120))
    url = Column(String(500))
    alt_text = Column(String(500))
    saved = Column(Boolean(), default=False)
    uploaded = Column(Boolean(), default=False)
    manufacturer_id = Column(Integer, ForeignKey('manufacturer.id'))
    parts = relationship('PartImages', back_populates='image')
    manufacturer = relationship('Manufacturer')

class Manufacturer(Base):
    __tablename__ = 'manufacturer'
    id = Column(Integer, primary_key=True)
    name = Column(String(300), index=True, unique=True)
    base_url = Column(String(300))
    parts = relationship('Part', backref='manufacturer', lazy=True)

class Part(Base):
    __tablename__ = 'part'
    id = Column(Integer, primary_key=True)
    url = Column(String(500))
    part_number = Column(String(200), index=True)
    manufacturer_id = Column(Integer, ForeignKey('manufacturer.id'))
    title = Column(String(200))
    category_id = Column(Integer, ForeignKey('category.id'))
    other_names = Column(Text())
    description = Column(Text())
    replaces = Column(Text())
    positions = Column(Text())
    notes = Column(Text())
    msrp = Column(Float())
    applications = Column(Text())
    hazmat = Column(Boolean)
    diagrams = relationship('DiagramParts', back_populates='part')
    images = relationship('PartImages', back_populates='part')

class Year(Base):
    __tablename__ = 'year'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)

class Make(Base):
    __tablename__ = 'make'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    select_value = Column(String(120))
    start_year = Column(Integer)
    end_year = Column(Integer)
    models = relationship('Model', backref='make', lazy=True)

class Model(Base):
    __tablename__ = 'model'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True)
    select_value = Column(String(120))
    make_id = Column(Integer, ForeignKey('make.id'))

class Trim(Base):
    __tablename__ = 'trim'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    select_value = Column(String(120))

class Engine(Base):
    __tablename__ = 'engine'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), index=True, unique=True)
    select_value = Column(String(120))

class Car(Base):
    __tablename__ = 'car'
    id = Column(Integer, primary_key=True)
    year_id = Column(Integer, ForeignKey('year.id'))
    make_id = Column(Integer, ForeignKey('make.id'))
    model_id = Column(Integer, ForeignKey('model.id'))
    trim_id = Column(Integer, ForeignKey('trim.id'))
    engine_id = Column(Integer, ForeignKey('engine.id'))
    manufacturer_id = Column(Integer, ForeignKey('manufacturer.id'))

    car_id = Column(String(200))
    vehicle_id = Column(String(200))
    base_url = Column(String(1000))

    year = relationship('Year', backref='cars', lazy=True)
    make = relationship('Make', backref='cars', lazy=True)
    model = relationship('Model', backref='cars', lazy=True)
    trim = relationship('Trim', backref='cars', lazy=True)
    engine = relationship('Engine', backref='cars', lazy=True)

    categories = relationship('Category', secondary=car_categories)
    diagrams = relationship('Diagram', secondary=car_diagrams, backref='car')
    parts = relationship('Part', secondary=car_parts)
    manufacturer = relationship('Manufacturer')

class Feedback(Base):
    __tablename__ = 'feedback'
    id = Column(Integer, primary_key=True)
    name = Column(String(250))
    email = Column(String(250))
    comments = Column(String(2000))

class Yard(Base):
    __tablename__ = 'yard'
    id = Column(Integer, primary_key=True)
    name = Column(String(1000), unique=True)

class YardLocation(Base):
    __tablename__ = 'yard_location'
    id = Column(Integer, primary_key=True)
    name = Column(String(1000), unique=True)
    yard_id = Column(Integer, ForeignKey('yard.id'))

    yard = relationship('Yard')

class ScrapeSession(Base):
    __tablename__ = 'scrape_session'
    id = Column(Integer, primary_key=True)
    yard_location_id = Column(Integer, ForeignKey('yard_location.id'))
    start_time = Column(DateTime)
    success = Column(Boolean)
    latest = Column(Boolean, index=True)

    yard_location = relationship('YardLocation')

class InventoryColor(Base):
    __tablename__ = 'inventory_color'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))

class InventoryTransType(Base):
    __tablename__ = 'inventory_trans_type'
    id = Column(Integer, primary_key=True)
    key = Column(String(10))
    name = Column(String(200))

class InventoryCar(Base):
    __tablename__ = 'inventory_car'
    id = Column(Integer, primary_key=True)
    yard_id = Column(Integer, ForeignKey('yard.id'))
    session_id = Column(Integer, ForeignKey('scrape_session.id'))
    year_id = Column(Integer, ForeignKey('year.id'))
    make_id = Column(Integer, ForeignKey('make.id'))
    model_id = Column(Integer, ForeignKey('model.id'))
    trim_id = Column(Integer, ForeignKey('trim.id'))
    engine_id = Column(Integer, ForeignKey('engine.id'))
    manufacturer_id = Column(Integer, ForeignKey('manufacturer.id'))
    color_id = Column(Integer, ForeignKey('inventory_color.id'))
    trans_type_id = Column(Integer, ForeignKey('inventory_trans_type.id'))

    vin = Column(String(30), unique=True)
    date_on_yard = Column(DateTime)
    trim = Column(String(200))
    fuel_type = Column(String(1))
    cylinders = Column(Integer)
    aspiration = Column(String(20))
    trans_speeds = Column(Integer)
    drive_type = Column(String(20))
    yard_notes = Column(String(1000))


    yard = relationship('Yard', lazy=True)
    scrape_session = relationship('ScrapeSession', lazy=True)
    year = relationship('Year', backref='inventory_cars', lazy=True)
    make = relationship('Make', backref='inventory_cars', lazy=True)
    model = relationship('Model', backref='inventory_cars', lazy=True)
    trim = relationship('Trim', backref='inventory_cars', lazy=True)
    engine = relationship('Engine', backref='inventory_cars', lazy=True)
    manufacturer = relationship('Manufacturer')
    color = relationship('InventoryColor')
    trans_type = relationship('InventoryTransType')

