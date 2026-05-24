"""
Common SQLAlchemy models shared across all junkyard inventory scrapers.
Every scraper writes into these tables using the common db session.
VehicleDetail has been eliminated — all fields are flat on Vehicle.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("source", "source_location_id", name="uq_location_source"),
    )

    id                 = Column(Integer,     primary_key=True, autoincrement=True)
    source             = Column(String(100), nullable=False, index=True)
    source_location_id = Column(String(100), nullable=False)
    name               = Column(String(200), nullable=False)
    chain              = Column(String(100), nullable=True)
    address            = Column(String(500), nullable=True)
    city               = Column(String(100), nullable=True)
    state              = Column(String(10),  nullable=True)
    zip_code           = Column(String(20),  nullable=True)
    phone              = Column(String(50),  nullable=True)
    lat                = Column(Float,       nullable=True)
    lng                = Column(Float,       nullable=True)
    is_active          = Column(Boolean,     nullable=False, default=True)
    first_seen_at      = Column(DateTime,    nullable=False)
    last_seen_at       = Column(DateTime,    nullable=False)

    vehicles    = relationship("Vehicle",   back_populates="location")
    scrape_runs = relationship("ScrapeRun", back_populates="location")

    def __repr__(self) -> str:
        return f"<Location {self.source!r} {self.name!r}>"


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("source", "source_key", name="uq_vehicle_source"),
    )

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    location_id = Column(Integer,     ForeignKey("locations.id"), nullable=False, index=True)
    source      = Column(String(100), nullable=False, index=True)
    source_key  = Column(String(200), nullable=False)

    # Core identity
    year         = Column(Integer,     nullable=True)
    make         = Column(String(100), nullable=True)
    model        = Column(String(200), nullable=True)
    vin          = Column(String(17),  nullable=True, index=True)
    row          = Column(String(20),  nullable=True)
    arrival_date = Column(DateTime,    nullable=True)
    color        = Column(String(100), nullable=True)

    # Formerly VehicleDetail — flattened in
    trim              = Column(String(200), nullable=True)
    vehicle_type      = Column(String(100), nullable=True)   # Car/Truck/SUV
    body_type         = Column(String(100), nullable=True)
    body_sub_type     = Column(String(100), nullable=True)
    doors             = Column(Integer,     nullable=True)
    style             = Column(String(200), nullable=True)
    drive_type        = Column(String(50),  nullable=True)   # FWD/RWD/AWD/4WD
    fuel_type         = Column(String(50),  nullable=True)   # G/D/E/H
    engine_block      = Column(String(10),  nullable=True)   # I/V/H
    engine_cylinders  = Column(Integer,     nullable=True)
    engine_size       = Column(Float,       nullable=True)    # litres
    engine_aspiration = Column(String(50),  nullable=True)   # N/A or T
    trans_type        = Column(String(10),  nullable=True)   # A/M/CVT
    trans_speeds      = Column(Integer,     nullable=True)
    mileage           = Column(Integer,     nullable=True)
    preview_image_url = Column(String(500), nullable=True)
    detail_fetched_at = Column(DateTime,    nullable=True)
    extras            = Column(JSONB,       nullable=True)    # yard-specific overflow

    # Car-ID mapping — populated by resolution pipeline (Phase 3)
    car_id            = Column(Integer,    nullable=True, index=True)
    car_id_resolved   = Column(Boolean,    nullable=False, default=False)
    car_id_method     = Column(String(20), nullable=True)    # vin_decode|ymmt_match|manual|rule_applied
    car_id_confidence = Column(Float,      nullable=True)

    # Bookkeeping
    is_active     = Column(Boolean,  nullable=False, default=True)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at  = Column(DateTime, nullable=False)

    location = relationship("Location", back_populates="vehicles")

    def __repr__(self) -> str:
        return f"<Vehicle {self.year} {self.make} {self.model} @ {self.source!r}>"


class MappingRule(Base):
    __tablename__ = "mapping_rules"

    id              = Column(Integer,      primary_key=True, autoincrement=True)
    scope           = Column(String(20),   nullable=False)    # global|source|location
    source          = Column(String(100),  nullable=True)
    location_id     = Column(Integer,      ForeignKey("locations.id"), nullable=True)
    field           = Column(String(50),   nullable=False)    # make|model|trim
    rule_type       = Column(String(20),   nullable=False)    # exact|prefix|regex
    raw_value       = Column(String(200),  nullable=False)
    canonical_value = Column(String(200),  nullable=False)
    make_context    = Column(String(100),  nullable=True)
    priority        = Column(Integer,      nullable=False, default=100)
    is_active       = Column(Boolean,      nullable=False, default=True)
    created_by      = Column(String(20),   nullable=False)    # manual|llm_suggested|import
    created_at      = Column(DateTime,     nullable=False)
    applied_count   = Column(Integer,      nullable=False, default=0)
    llm_confidence  = Column(Float,        nullable=True)
    llm_rationale   = Column(String(1000), nullable=True)
    approved_at     = Column(DateTime,     nullable=True)
    approved_by     = Column(String(100),  nullable=True)


class MappingDiscrepancy(Base):
    __tablename__ = "mapping_discrepancies"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_discrepancy_vehicle"),
    )

    id         = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"),      nullable=False)
    raw_year   = Column(String(20),  nullable=True)
    raw_make   = Column(String(100), nullable=True)
    raw_model  = Column(String(200), nullable=True)
    raw_trim   = Column(String(200), nullable=True)

    fuzzy_make_match  = Column(String(100), nullable=True)
    fuzzy_make_score  = Column(Float,       nullable=True)
    fuzzy_model_match = Column(String(200), nullable=True)
    fuzzy_model_score = Column(Float,       nullable=True)
    candidate_car_id  = Column(Integer,     nullable=True)

    # unresolved | pending_rule | rule_applied | manual | ignored | no_match_in_dataset
    status = Column(String(30), nullable=False, default="unresolved")

    resolved_car_id     = Column(Integer,  nullable=True)
    resolved_by_rule_id = Column(Integer,  ForeignKey("mapping_rules.id"), nullable=True)
    resolved_at         = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, nullable=False)
    last_processed_at   = Column(DateTime, nullable=True)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id            = Column(Integer,      primary_key=True, autoincrement=True)
    source        = Column(String(100),  nullable=False, index=True)
    location_id   = Column(Integer,      ForeignKey("locations.id"), nullable=True)
    started_at    = Column(DateTime,     nullable=False)
    completed_at  = Column(DateTime,     nullable=True)
    total_in_feed = Column(Integer,      nullable=True)
    new_vehicles     = Column(Integer,   nullable=False, default=0)
    updated_vehicles = Column(Integer,   nullable=False, default=0)
    removed_vehicles = Column(Integer,   nullable=False, default=0)
    success       = Column(Boolean,      nullable=False, default=False)
    error_message = Column(String(1000), nullable=True)

    location = relationship("Location", back_populates="scrape_runs")


class VinCache(Base):
    __tablename__ = "vin_cache"

    vin         = Column(String(17),  primary_key=True)
    make        = Column(String(100), nullable=True)
    model       = Column(String(200), nullable=True)
    model_year  = Column(String(10),  nullable=True)
    trim        = Column(String(200), nullable=True)
    error_code  = Column(String(20),  nullable=True)   # "11" for pre-1980; "INCOMPLETE" for bad decode
    fetched_at  = Column(DateTime,    nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<VinCache {self.vin!r} {self.make} {self.model_year}>"
