from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import bcrypt  # <-- আমরা এখন সরাসরি bcrypt ব্যবহার করব

from app.database import engine, get_db
from app.models import models

# টেবিল তৈরি (যদি না থাকে)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# --- Routes ---

@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    # কুকি থেকে ইউজার চেক করা
    user_email = request.cookies.get("user_email")
    current_user = None
    
    if user_email:
        current_user = db.query(models.User).filter(models.User.email == user_email).first()
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "user": current_user  # ইউজার ডাটা html এ পাঠালাম
    })

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register_user(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    university: str = Form(...),
    db: Session = Depends(get_db)
):
    # ১. পাসওয়ার্ড এনক্রিপ্ট (Hashing) - নতুন পদ্ধতি
    # bcrypt.hashpw বাইট চায়, তাই encode() করছি। শেষে আবার decode() করছি স্ট্রিং হিসেবে সেভ করতে।
    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_password = hashed_bytes.decode('utf-8')
    
    # ২. ইউজার তৈরি
    new_user = models.User(
        username=username,
        email=email,
        password=hashed_password,
        university=university
    )
    
    # ৩. সেভ করা
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    print(f"User Created Successfully: {username}")
    
    # ৪. সফল হলে হোমপেজে পাঠাও
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# --- Login Routes ---

# ১. লগিন পেজ দেখানোর জন্য
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# ২. লগিন চেক করার জন্য
@app.post("/login")
def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # ইমেইল দিয়ে ইউজার খুঁজছি
    user = db.query(models.User).filter(models.User.email == email).first()
    
    # ইউজার না পেলে বা পাসওয়ার্ড ভুল হলে
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })
    
    # সব ঠিক থাকলে কুকি সেট করব (লগিন মনে রাখার জন্য)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="user_email", value=user.email)  # কুকিতে ইমেইল রাখলাম
    return response

# ৩. লগআউট (Logout)
@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("user_email")
    return response