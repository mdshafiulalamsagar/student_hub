from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# ১. ইউজার টেবিল (Users Table)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)  # আমরা পরে এটাকে হ্যাশ করে রাখব
    university = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # সম্পর্ক: একজন ইউজারের অনেকগুলো নোট থাকতে পারে
    resources = relationship("Resource", back_populates="uploader")

# ২. রিসোর্স টেবিল (Resources/Notes Table)
class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    course_name = Column(String)
    description = Column(Text, nullable=True)
    file_url = Column(String)  # সুপাবেস স্টোরেজের লিংক
    category = Column(String)  # Note, Question, Suggestion
    
    # কে আপলোড দিয়েছে? (Foreign Key)
    uploader_id = Column(Integer, ForeignKey("users.id"))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # সম্পর্ক: এই নোটটা কোন ইউজারের
    uploader = relationship("User", back_populates="resources")