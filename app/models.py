from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from .db import Base

class Person(Base):
    __tablename__ = "people"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Fixture(Base):
    __tablename__ = "fixtures"
    id = Column(Integer, primary_key=True)
    gameweek = Column(Integer, index=True, nullable=False)
    api_match_id = Column(Integer, unique=True, index=True, nullable=False)
    kickoff_utc = Column(String, nullable=True)
    home = Column(String, nullable=False)
    away = Column(String, nullable=False)

class Result(Base):
    __tablename__ = "results"
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), primary_key=True)
    act_home = Column(Integer, nullable=True)
    act_away = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), index=True, nullable=False)
    gameweek = Column(Integer, index=True, nullable=False)
    person_name = Column(String, index=True, nullable=False)
    pred_home = Column(Integer, nullable=False)
    pred_away = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("fixture_id","person_name", name="uq_prediction_fixture_person"),)
