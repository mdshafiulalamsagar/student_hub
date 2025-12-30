import os
from fastapi import FastAPI, Request, Form, Depends, status, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import bcrypt
import smtplib
import random
from email.mime.text import MIMEText
from datetime import datetime
from supabase import create_client, Client

from app.database import engine, get_db
from app.models import models

# ১. ডাটাবেস টেবিল তৈরি (যদি না থাকে)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- ২. কনফিগারেশন (Static Files Fix for Vercel) ---
# বর্তমান ফাইলের লোকেশন বের করছি
script_dir = os.path.dirname(__file__)
# static ফোল্ডারের পূর্ণ ঠিকানা (Absolute Path) তৈরি করছি
static_abs_path = os.path.join(script_dir, "static")

# যদি static ফোল্ডার না থাকে, তবে তৈরি করে নিবে (সেফটি চেক)
if not os.path.isdir(static_abs_path):
    os.makedirs(static_abs_path)

# Static Files Mount করা
app.mount("/static", StaticFiles(directory=static_abs_path), name="static")

templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ৩. Supabase সেটআপ
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ৪. ইমেইল পাঠানোর ফাংশন ---
def send_email_code(to_email: str, code: str):
    sender_email = os.getenv("MAIL_USERNAME")
    sender_password = os.getenv("MAIL_PASSWORD")
    
    subject = "Verification Code - Student Hub"
    body = f"Hello,\n\nYour verification code is: {code}\n\nUse this code to complete your registration."
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to_email

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Email Failed: {e}")

# --- ৫. রাউটস (Routes) ---

# হোমপেজ
@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_email")
    current_user = None
    if user_email:
        current_user = db.query(models.User).filter(models.User.email == user_email).first()
    
    all_notes = db.query(models.Resource).order_by(models.Resource.created_at.desc()).all()
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "user": current_user, 
        "notes": all_notes
    })

# --- রেজিস্ট্রেশন ফ্লো (Registration Flow) ---

# ধাপ ১: ইমেইল পেজ দেখানো
@app.get("/register")
def verify_email_page(request: Request):
    return templates.TemplateResponse("verify_email.html", {"request": request})

# ধাপ ২: কোড পাঠানো (OTP Send)
@app.post("/send-otp")
def send_otp(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    # ডোমেইন ভ্যালিডেশন (Domain Check)
    allowed_domains = [".edu.bd", ".ac.bd", ".edu"] 
    
    is_valid_domain = False
    for domain in allowed_domains:
        if email.endswith(domain):
            is_valid_domain = True
            break
            
    if not is_valid_domain:
        return templates.TemplateResponse("verify_email.html", {
            "request": request, 
            "error": "Error: Only university emails (.edu.bd, .ac.bd) are allowed!"
        })

    # ডুপ্লিকেট ইমেইল চেক
    if db.query(models.User).filter(models.User.email == email).first():
         return templates.TemplateResponse("verify_email.html", {
             "request": request, 
             "error": "Email already registered! Please Login."
         })

    # কোড জেনারেট ও সেভ
    code = str(random.randint(100000, 999999))
    db.query(models.OTP).filter(models.OTP.email == email).delete()
    
    new_otp = models.OTP(email=email, code=code)
    db.add(new_otp)
    db.commit()
    
    # ইমেইল পাঠানো
    send_email_code(email, code)
    
    return templates.TemplateResponse("verify_code.html", {"request": request, "email": email})

# ধাপ ৩: কোড ভেরিফাই (Verify OTP)
@app.post("/verify-otp")
def verify_otp(request: Request, email: str = Form(...), code: str = Form(...), db: Session = Depends(get_db)):
    otp_record = db.query(models.OTP).filter(models.OTP.email == email, models.OTP.code == code).first()
    
    if not otp_record:
        return templates.TemplateResponse("verify_code.html", {
            "request": request, "email": email, "error": "Invalid Code! Try again."
        })
    
    return templates.TemplateResponse("register.html", {"request": request, "email": email})

# ধাপ ৪: ফাইনাল রেজিস্ট্রেশন (Create Account)
@app.post("/register")
def register_final(
    full_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    university: str = Form(...),
    department: str = Form(...),
    batch: str = Form(...),
    db: Session = Depends(get_db)
):
    if db.query(models.User).filter(models.User.username == username).first():
        return "Username taken! Go back."

    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_password = hashed_bytes.decode('utf-8')
    
    new_user = models.User(
        full_name=full_name,
        username=username,
        email=email,
        password=hashed_password,
        university=university,
        department=department,
        batch=batch
    )
    
    db.add(new_user)
    db.query(models.OTP).filter(models.OTP.email == email).delete() # OTP মুছে ফেলা
    db.commit()
    
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

# --- লগিন ও লগআউট ---
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

# --- প্রোফাইল পেজ ---
@app.get("/profile")
def profile_page(request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_email")
    if not user_email:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    user = db.query(models.User).filter(models.User.email == user_email).first()
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

# --- ফাইল আপলোড ---
@app.get("/upload")
def upload_page(request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_email")
    if not user_email:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    user = db.query(models.User).filter(models.User.email == user_email).first()
    return templates.TemplateResponse("upload.html", {"request": request, "user": user})

@app.post("/upload")
async def upload_file(
    title: str = Form(...), category: str = Form(...), course_name: str = Form(...),
    file: UploadFile = File(...), request: Request = Request, db: Session = Depends(get_db)
):
    user_email = request.cookies.get("user_email")
    if not user_email: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    user = db.query(models.User).filter(models.User.email == user_email).first()

    unique_filename = f"{datetime.now().timestamp()}_{file.filename}"
    file_content = await file.read()
    bucket_name = "notes"
    
    try:
        supabase.storage.from_(bucket_name).upload(path=unique_filename, file=file_content, file_options={"content-type": file.content_type})
    except Exception as e:
        print(f"Upload Error: {e}")
        return "File upload failed! Check Vercel logs."

    public_url = supabase.storage.from_(bucket_name).get_public_url(unique_filename)
    new_note = models.Resource(
        title=title, category=category, course_name=course_name,
        file_url=public_url, uploader_id=user.id
    )
    db.add(new_note)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)