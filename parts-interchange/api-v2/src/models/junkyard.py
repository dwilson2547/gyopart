# api-v2/src/models/junkyard.py
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.database import Base


class Junkyard(Base):
    __tablename__ = "junkyard"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    address = Column(Text)
    city = Column(Text)
    state = Column(Text)
    zip = Column(Text)
    lat = Column(Float)
    lng = Column(Float)
    phone = Column(Text)
    website = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    inventory = relationship("JunkyardInventory", back_populates="junkyard", lazy="noload")


class ScrapeConfig(Base):
    __tablename__ = "scrape_site_config"
    id = Column(Integer, primary_key=True)
    junkyard_id = Column(Integer, ForeignKey("junkyard.id"))
    site_type = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    scrape_interval_hours = Column(Integer, default=24)
    enabled = Column(Boolean, default=True)
    last_scraped_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    junkyard = relationship("Junkyard")
    jobs = relationship("ScrapeJob", back_populates="config", lazy="noload")


class ScrapeJob(Base):
    __tablename__ = "scrape_job"
    id = Column(Integer, primary_key=True)
    scrape_site_config_id = Column(Integer, ForeignKey("scrape_site_config.id"))
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    config = relationship("ScrapeConfig", back_populates="jobs")


class JunkyardInventory(Base):
    __tablename__ = "junkyard_inventory"
    id = Column(Integer, primary_key=True)
    junkyard_id = Column(Integer, ForeignKey("junkyard.id"), nullable=False)
    scrape_job_id = Column(Integer, ForeignKey("scrape_job.id"))
    year = Column(Text, nullable=False)
    make_name = Column(Text, nullable=False)
    model_name = Column(Text, nullable=False)
    trim_name = Column(Text)
    date_listed = Column(Date)
    date_removed = Column(Date)
    price = Column(Numeric(10, 2))
    row_location = Column(Text)
    vin = Column(Text)
    raw_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    junkyard = relationship("Junkyard", back_populates="inventory")
