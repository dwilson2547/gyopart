from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Base(db.Model):
    __abstract__ = True
    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

car_categories = db.Table('car_categories',
    db.Column('car_id', db.Integer, db.ForeignKey('car.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True))

car_diagrams = db.Table('car_diagrams',
    db.Column('car_id', db.Integer, db.ForeignKey('car.id'), primary_key=True),
    db.Column('diagram_id', db.Integer, db.ForeignKey('diagram.id'), primary_key=True))

car_parts = db.Table('car_parts',
    db.Column('car_id', db.Integer, db.ForeignKey('car.id'), primary_key=True),
    db.Column('part_id', db.Integer, db.ForeignKey('part.id'), primary_key=True))

class PartImages(Base):
    __tablename__ = 'part_images'

    # id = db.Column(db.Integer, primary_key=True)
    # part_id = db.Column(db.Integer, db.ForeignKey('part.id'))
    # main_id = db.Column(db.Integer, db.ForeignKey('image.id'))
    # preview_id = db.Column(db.Integer, db.ForeignKey('image.id'))
    # thumb_id = db.Column(db.Integer, db.ForeignKey('image.id'))

    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'), primary_key=True)
    
    part_image_text = db.Column(db.String(500))
    image = db.relationship('Image', back_populates='parts')
    part = db.relationship('Part', back_populates='images')

class DiagramParts(Base):
    __tablename__ = 'diagram_parts'
    diagram_id = db.Column(db.Integer, db.ForeignKey('diagram.id'), primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey('part.id'), primary_key=True)
    part_index = db.Column(db.String(25))
    part = db.relationship('Part', back_populates='diagrams')
    diagram = db.relationship('Diagram', back_populates='parts')

class Category(Base):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True, unique=True)

class SubCategory(Base):
    __tablename__ = 'subcategory'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    category = db.relationship('Category', backref='sub_categories')

class Diagram(Base):
    __tablename__ = 'diagram'
    id = db.Column(db.Integer(), primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    sub_category_id = db.Column(db.Integer, db.ForeignKey('subcategory.id'))
    base_car_url = db.Column(db.String(1000))
    category_url = db.Column(db.String(1000))
    image = db.relationship('Image')
    parts = db.relationship('DiagramParts', back_populates='diagram')
    category = db.relationship('Category')
    sub_category = db.relationship('SubCategory')

class Image(Base):
    __tablename__ = 'image'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), index=True)
    bucket_path = db.Column(db.String(120))
    url = db.Column(db.String(500))
    alt_text = db.Column(db.String(500))
    saved = db.Column(db.Boolean(), default=False)
    uploaded = db.Column(db.Boolean(), default=False)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturer.id'))
    parts = db.relationship('PartImages', back_populates='image')
    manufacturer = db.relationship('Manufacturer')

class Manufacturer(Base):
    __tablename__ = 'manufacturer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), index=True, unique=True)
    base_url = db.Column(db.String(300))
    parts = db.relationship('Part', backref='manufacturer', lazy=True)

class Part(Base):
    __tablename__ = 'part'
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500))
    part_number = db.Column(db.String(200), index=True)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturer.id'))
    title = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    other_names = db.Column(db.Text())
    description = db.Column(db.Text())
    replaces = db.Column(db.Text())
    positions = db.Column(db.Text())
    notes = db.Column(db.Text())
    msrp = db.Column(db.Float())
    applications = db.Column(db.Text())
    hazmat = db.Column(db.Boolean)
    diagrams = db.relationship('DiagramParts', back_populates='part')
    images = db.relationship('PartImages', back_populates='part')

class Year(Base):
    __tablename__ = 'year'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True, unique=True)

class Make(Base):
    __tablename__ = 'make'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True, unique=True)
    select_value = db.Column(db.String(120))
    start_year = db.Column(db.Integer)
    end_year = db.Column(db.Integer)
    models = db.relationship('Model', backref='make', lazy=True)

class Model(Base):
    __tablename__ = 'model'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True)
    select_value = db.Column(db.String(120))
    make_id = db.Column(db.Integer, db.ForeignKey('make.id'))
    # make = backref

class Trim(Base):
    __tablename__ = 'trim'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True, unique=True)
    select_value = db.Column(db.String(120))

class Engine(Base):
    __tablename__ = 'engine'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True, unique=True)
    select_value = db.Column(db.String(120))

class Car(Base):
    __tablename__ = 'car'
    id = db.Column(db.Integer, primary_key=True)
    year_id = db.Column(db.Integer, db.ForeignKey('year.id'))
    make_id = db.Column(db.Integer, db.ForeignKey('make.id'))
    model_id = db.Column(db.Integer, db.ForeignKey('model.id'))
    trim_id = db.Column(db.Integer, db.ForeignKey('trim.id'))
    engine_id = db.Column(db.Integer, db.ForeignKey('engine.id'))
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturer.id'))

    car_id = db.Column(db.String(200))
    vehicle_id = db.Column(db.String(200))
    base_url = db.Column(db.String(1000))

    year = db.relationship('Year', backref='cars', lazy=True)
    make = db.relationship('Make', backref='cars', lazy=True)
    model = db.relationship('Model', backref='cars', lazy=True)
    trim = db.relationship('Trim', backref='cars', lazy=True)
    engine = db.relationship('Engine', backref='cars', lazy=True)

    categories = db.relationship('Category', secondary=car_categories)
    diagrams = db.relationship('Diagram', secondary=car_diagrams, backref='car')
    parts = db.relationship('Part', secondary=car_parts)
    manufacturer = db.relationship('Manufacturer')

class Feedback(Base):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250))
    email = db.Column(db.String(250))
    comments = db.Column(db.String(2000))