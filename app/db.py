import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = os.getenv("DB_PATH", "/data/app.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
