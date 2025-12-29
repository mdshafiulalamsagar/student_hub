from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# .env ফাইল থেকে লিংকটা লোড করছি
load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# ইঞ্জিনে কানেকশন দিচ্ছি
engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ডাটাবেস সেশন পাওয়ার জন্য একটি ছোট ফাংশন
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()