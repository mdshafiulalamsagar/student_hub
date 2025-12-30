from fastapi import FastAPI, Request, Form, Depends, status, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import bcrypt
import os
from datetime import datetime
from supabase import create_client, Client # সুপাবেস লাইব্রেরি

from app.database import engine, get_db
from app.models import models

# টেবিল তৈরি (যদি না থাকে)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- কনফিগারেশন ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Supabase সেটআপ
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Routes ---

@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_email")
    current_user = None
    if user_email:
        current_user = db.query(models.User).filter(models.User.email == user_email).first()
    
    # সব নোট ডাটাবেস থেকে তুলে আনছি (হোমপেজে দেখানোর জন্য)
    all_notes = db.query(models.Resource).order_by(models.Resource.created_at.desc()).all()
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "user": current_user,
        "notes": all_notes
    })

# --- Auth Routes (Register & Login) ---
@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register_user(username: str = Form(...), email: str = Form(...), password: str = Form(...), university: str = Form(...), db: Session = Depends(get_db)):
    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_password = hashed_bytes.decode('utf-8')
    new_user = models.User(username=username, email=email, password=hashed_password, university=university)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_user(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password"})
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="user_email", value=user.email)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("user_email")
    return response

# --- Upload Routes (আসল কাজ) ---
@app.get("/upload")
def upload_page(request: Request, db: Session = Depends(get_db)):
    # ১. কুকি চেক করা
    user_email = request.cookies.get("user_email")
    if not user_email:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # ২. ডাটাবেস থেকে ইউজার খুঁজে বের করা (এই লাইনটা মিসিং ছিল)
    user = db.query(models.User).filter(models.User.email == user_email).first()
        
    # ৩. টেমপ্লেটে 'user' ভেরিয়েবল পাঠানো
    return templates.TemplateResponse("upload.html", {"request": request, "user": user})

@app.post("/upload")
async def upload_file(
    title: str = Form(...),
    category: str = Form(...),
    course_name: str = Form(...),
    file: UploadFile = File(...),
    request: Request = Request,
    db: Session = Depends(get_db)
):
    # ১. ইউজার চেক করা
    user_email = request.cookies.get("user_email")
    if not user_email:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    user = db.query(models.User).filter(models.User.email == user_email).first()

    # ২. ফাইলের নাম ইউনিক করা (যাতে এক নামের দুই ফাইল মারামারি না করে)
    # যেমন: algo.pdf হয়ে যাবে -> 17123456_algo.pdf
    unique_filename = f"{datetime.now().timestamp()}_{file.filename}"

    # ৩. ফাইল পড়া এবং Supabase এ আপলোড করা
    file_content = await file.read()
    bucket_name = "notes" # আমরা সুপাবেসে এই নামটাই দিয়েছিলাম
    
    try:
        supabase.storage.from_(bucket_name).upload(
            path=unique_filename,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
    except Exception as e:
        print(f"Upload Error: {e}")
        return "File upload failed! Check terminal for error."

    # ৪. পাবলিক লিংক জেনারেট করা
    public_url = supabase.storage.from_(bucket_name).get_public_url(unique_filename)

    # ৫. ডাটাবেসে সেভ করা
    new_note = models.Resource(
        title=title,
        category=category,
        course_name=course_name,
        file_url=public_url,
        uploader_id=user.id
    )
    db.add(new_note)
    db.commit()
    
    print("Success! File uploaded and saved to DB.")
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)