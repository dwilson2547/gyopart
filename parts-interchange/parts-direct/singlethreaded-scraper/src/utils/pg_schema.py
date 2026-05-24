from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, MetaData, String, Table, Text,
)

metadata = MetaData()

manufacturer_table = Table("manufacturer", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(300), nullable=False, unique=True),
    Column("base_url", String(300)),
)

year_table = Table("year", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
)

make_table = Table("make", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("select_value", String(120)),
    Column("start_year", Integer),
    Column("end_year", Integer),
)

model_table = Table("model", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("select_value", String(120)),
    Column("make_id", Integer, ForeignKey("make.id")),
)

trim_table = Table("trim", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("select_value", String(120)),
)

engine_table = Table("engine", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("select_value", String(120)),
)

car_table = Table("car", metadata,
    Column("id", Integer, primary_key=True),
    Column("year_id", Integer, ForeignKey("year.id")),
    Column("make_id", Integer, ForeignKey("make.id")),
    Column("model_id", Integer, ForeignKey("model.id")),
    Column("trim_id", Integer, ForeignKey("trim.id")),
    Column("engine_id", Integer, ForeignKey("engine.id")),
    Column("manufacturer_id", Integer, ForeignKey("manufacturer.id")),
    Column("car_id", String(200)),
    Column("vehicle_id", String(200)),
    Column("base_url", String(1000)),
)

category_table = Table("category", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
)

subcategory_table = Table("subcategory", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("category_id", Integer, ForeignKey("category.id")),
)

diagram_table = Table("diagram", metadata,
    Column("id", Integer, primary_key=True),
    Column("image_id", Integer, ForeignKey("image.id")),
    Column("category_id", Integer, ForeignKey("category.id")),
    Column("sub_category_id", Integer, ForeignKey("subcategory.id")),
    Column("base_car_url", String(1000)),
    Column("category_url", String(1000)),
)

image_table = Table("image", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("bucket_path", String(120)),
    Column("url", String(500)),
    Column("alt_text", String(500)),
    Column("saved", Boolean, default=False),
    Column("uploaded", Boolean, default=False),
    Column("manufacturer_id", Integer, ForeignKey("manufacturer.id")),
    Column("imgcache_hash", String(64)),
    Column("imgcache_bucket", String(100)),
)

part_table = Table("part", metadata,
    Column("id", Integer, primary_key=True),
    Column("url", String(500)),
    Column("part_number", String(200)),
    Column("manufacturer_id", Integer, ForeignKey("manufacturer.id")),
    Column("title", String(200)),
    Column("category_id", Integer, ForeignKey("category.id")),
    Column("other_names", Text()),
    Column("description", Text()),
    Column("replaces", Text()),
    Column("positions", Text()),
    Column("notes", Text()),
    Column("msrp", Float()),
    Column("applications", Text()),
    Column("hazmat", Boolean),
)

car_parts_table = Table("car_parts", metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
)

diagram_parts_table = Table("diagram_parts", metadata,
    Column("diagram_id", Integer, ForeignKey("diagram.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
    Column("part_index", String(25)),
)

part_images_table = Table("part_images", metadata,
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
    Column("image_id", Integer, ForeignKey("image.id"), primary_key=True),
    Column("part_image_text", String(500)),
)

scrape_run_table = Table("scrape_run", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("manufacturer", String(100), nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("completed_at", DateTime),
    Column("cars_processed", Integer, default=0),
    Column("new_parts", Integer, default=0),
    Column("updated_parts", Integer, default=0),
    Column("success", Boolean, nullable=False, default=False),
    Column("error_message", String(1000)),
)
