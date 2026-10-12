from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import User, RegistrationState, OTPCode
import secrets
from datetime import datetime, timezone
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.core.email import send_email_sync
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
import jwt
import httpx
from datetime import timedelta
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

class RegisterStep1(BaseModel):
    email: str

class RegisterStep2(BaseModel):
    email: str
    password: str
    confirm_password: str

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str

class GoogleTokenAuthRequest(BaseModel):
    id_token: Optional[str] = None
    access_token: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str
    confirm_password: str

def generate_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(6))

@router.post("/register/step1", status_code=status.HTTP_200_OK)
async def register_step1(data: RegisterStep1, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    result = await db.execute(select(RegistrationState).where(RegistrationState.email == data.email))
    reg_state = result.scalars().first()
    
    if not reg_state:
        reg_state = RegistrationState(email=data.email, step=1)
        db.add(reg_state)
    else:
        reg_state.step = 1
        reg_state.hashed_password = None
    
    await db.commit()
    return {"message": "Step 1 complete. Proceed to step 2."}

@router.post("/register/step2", status_code=status.HTTP_200_OK)
async def register_step2(data: RegisterStep2, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
        
    result = await db.execute(select(RegistrationState).where(RegistrationState.email == data.email))
    reg_state = result.scalars().first()
    
    if not reg_state or reg_state.step < 1:
        raise HTTPException(status_code=400, detail="Please complete step 1 first")
        
    reg_state.step = 2
    reg_state.hashed_password = get_password_hash(data.password)
    
    # Generate OTP
    otp_val = generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    otp_record = OTPCode(email=data.email, code=otp_val, purpose='register', expires_at=expires)
    db.add(otp_record)
    
    await db.commit()
    
    # Send email in background
    subject = "CognAI Registration - Your Verification Code"
    body = f"Hello,\n\nYour registration verification code is: {otp_val}\n\nThis code will expire in 15 minutes.\n\nThank you,\nCognAI Team"
    background_tasks.add_task(send_email_sync, data.email, subject, body)
    
    return {"message": "OTP sent to email. Please verify."}

class ResendOTPRequest(BaseModel):
    email: str

@router.post("/register/resend-otp", status_code=status.HTTP_200_OK)
async def register_resend_otp(data: ResendOTPRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RegistrationState).where(RegistrationState.email == data.email))
    reg_state = result.scalars().first()
    
    if not reg_state or reg_state.step < 2:
        raise HTTPException(status_code=400, detail="Registration state invalid")

    otp_val = generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    otp_record = OTPCode(email=data.email, code=otp_val, purpose='register', expires_at=expires)
    db.add(otp_record)
    
    await db.commit()
    
    subject = "CognAI Registration - Your Verification Code (Resent)"
    body = f"Hello,\n\nYour registration verification code is: {otp_val}\n\nThis code will expire in 15 minutes.\n\nThank you,\nCognAI Team"
    background_tasks.add_task(send_email_sync, data.email, subject, body)
    
    return {"message": "OTP resent to email. Please verify."}

@router.post("/register/verify-otp", status_code=status.HTTP_201_CREATED)
async def register_verify_otp(data: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OTPCode).where(
            OTPCode.email == data.email, 
            OTPCode.code == data.otp, 
            OTPCode.purpose == 'register'
        ).order_by(OTPCode.created_at.desc())
    )
    otp_record = result.scalars().first()
    
    if not otp_record or otp_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
    result = await db.execute(select(RegistrationState).where(RegistrationState.email == data.email))
    reg_state = result.scalars().first()
    
    if not reg_state or reg_state.step != 2:
        raise HTTPException(status_code=400, detail="Registration state invalid")
        
    # Check if user already created
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    db_user = User(
        email=data.email, 
        hashed_password=reg_state.hashed_password,
        is_verified=True
    )
    db.add(db_user)
    
    # Clean up
    await db.delete(reg_state)
    await db.delete(otp_record)
    
    await db.commit()
    return {"message": "User registered and verified successfully"}

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    
    if not user_info:
        raise HTTPException(status_code=400, detail="Could not fetch user info from Google")
        
    email = user_info.get("email")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user:
        # Create user without password
        user = User(email=email, is_verified=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/google", status_code=status.HTTP_200_OK)
async def google_token_auth(req: GoogleTokenAuthRequest, db: AsyncSession = Depends(get_db)):
    """
    Direct Google Token verification for mobile and web apps.
    Accepts id_token or access_token from GoogleSignIn SDK, verifies with Google,
    and returns signed CognAI JWT.
    """
    email = None
    
    if req.id_token:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={req.id_token}")
                if resp.status_code == 200:
                    data = resp.json()
                    email = data.get("email")
                    aud = data.get("aud")
                    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_ID != "your_google_client_id_here":
                        if aud != settings.GOOGLE_CLIENT_ID:
                            raise HTTPException(status_code=400, detail="Invalid token audience")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Google token verification failed: {e}")
                
    if not email and req.access_token:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {req.access_token}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    email = data.get("email")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Google userinfo verification failed: {e}")

    if not email:
        raise HTTPException(status_code=400, detail="Could not verify Google authentication token")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    
    if not user:
        user = User(email=email, is_verified=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    if user.deletion_pending:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is pending deletion.")

    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/config")
async def get_auth_config():
    """Returns public client configuration (e.g. Google Client ID) so clients don't need manual config."""
    client_id = settings.GOOGLE_CLIENT_ID
    if client_id == "your_google_client_id_here":
        client_id = None
    return {
        "google_client_id": client_id
    }

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    if user:
        otp_val = generate_otp()
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        otp_record = OTPCode(email=req.email, code=otp_val, purpose='forget_password', expires_at=expires)
        db.add(otp_record)
        await db.commit()
        
        subject = "CognAI - Password Reset Request"
        body = f"Hello,\n\nYou requested a password reset. Your OTP is: {otp_val}\n\nThis code will expire in 15 minutes.\n\nThank you,\nCognAI Team"
        background_tasks.add_task(send_email_sync, req.email, subject, body)
    
    # Always return a generic success message to prevent email enumeration
    return {"message": "If that email is registered, a password reset OTP has been sent."}

@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    result = await db.execute(
        select(OTPCode).where(
            OTPCode.email == req.email, 
            OTPCode.code == req.otp, 
            OTPCode.purpose == 'forget_password'
        ).order_by(OTPCode.created_at.desc())
    )
    otp_record = result.scalars().first()
    
    if not otp_record or otp_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.hashed_password = get_password_hash(req.new_password)
    await db.delete(otp_record)
    await db.commit()
    return {"message": "Password has been successfully reset."}


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    if user.deletion_pending:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is pending deletion.")
    return user


async def get_user_from_token(token: str, db: AsyncSession) -> Optional[User]:
    """Helper to validate JWT token for WebSocket connections."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user and user.deletion_pending:
            return None
        return user
    except Exception:
        return None

