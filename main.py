from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import bcrypt
import mimetypes

# ==========================================
# 1. FastAPI 및 CORS 설정
# ==========================================
# FastAPI 앱과 HTML·폰트 파일의 기준 경로를 초기화합니다.
app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
mimetypes.add_type("font/woff2", ".woff2")
app.mount("/fonts", StaticFiles(directory=BASE_DIR / "public" / "fonts"), name="fonts")

# 브라우저 화면과 API가 다른 주소에서 실행되는 개발 환경을 허용합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
async def serve_home():
    """서비스 소개와 시작 버튼을 제공하는 메인 화면을 반환합니다."""
    return FileResponse(BASE_DIR / "home.html", headers={"Cache-Control": "no-store"})

@app.get("/editor", include_in_schema=False)
async def serve_editor():
    """로그인, 회원가입, 포트폴리오 편집 기능이 있는 마이페이지를 반환합니다."""
    return FileResponse(BASE_DIR / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/mindmap", include_in_schema=False)
async def serve_mindmap():
    """저장된 포트폴리오를 시각화하는 마인드맵 화면을 반환합니다."""
    return FileResponse(BASE_DIR / "mindmap.html", headers={"Cache-Control": "no-store"})

# ==========================================
# 2. 데이터베이스 설정
# ==========================================
LOCAL_DATABASE_URL = f"sqlite:///{(BASE_DIR / 'portfolio.db').as_posix()}"
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", LOCAL_DATABASE_URL)

# Render Postgres의 기본 연결 문자열(postgresql://)을 psycopg 드라이버 형식으로 변환합니다.
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine_options = {"pool_pre_ping": True}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# DB 테이블 모델 정의: 회원 계정과 저장된 포트폴리오를 분리해 관리합니다.
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    hashed_password = Column(String)

class PortfolioDB(Base):
    __tablename__ = "portfolios"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    content = Column(String) # JSON 형태로 저장

# 테이블 생성 (서버 실행 시 portfolio.db 파일이 자동 생성됨)
Base.metadata.create_all(bind=engine)

# DB 세션 의존성 주입 함수
def get_db():
    """요청마다 데이터베이스 세션을 열고 응답 후 안전하게 닫습니다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 3. 보안 및 JWT 토큰 설정
# ==========================================
SECRET_KEY = os.getenv("SECRET_KEY", "local-development-only-change-this-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# 프론트엔드에서 로그인 데이터를 보낼 엔드포인트 지정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password):
    """평문 비밀번호를 bcrypt 해시 문자열로 변환합니다."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, hashed_password):
    """입력한 비밀번호와 저장된 bcrypt 해시가 일치하는지 확인합니다."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data: dict):
    """사용자 이메일과 만료 시간을 포함한 JWT 로그인 토큰을 생성합니다."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# 현재 로그인한 사용자 확인 함수 (API 보호용)
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Bearer 토큰을 검증하고, 토큰의 이메일에 해당하는 로그인 사용자를 반환합니다."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않은 토큰입니다. 다시 로그인해주세요.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

# ==========================================
# 4. Pydantic 스키마 (요청 데이터 검증용)
# ==========================================
class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str

class ProjectInput(BaseModel):
    """포트폴리오에 포함되는 프로젝트 한 건의 제목과 설명입니다."""
    title: str
    description: str

class PortfolioInput(BaseModel):
    """마이페이지에서 저장하는 포트폴리오 전체 입력값입니다."""
    name: str
    role: str
    strength: str
    skills: str
    projects: list[ProjectInput] = []

# ==========================================
# 5. API 엔드포인트
# ==========================================

# [API] 회원가입
@app.post("/signup")
async def signup(user: UserCreate, db: Session = Depends(get_db)):
    """새 사용자 이메일을 중복 확인한 뒤 암호화된 비밀번호와 함께 저장합니다."""
    # 이메일 중복 검사
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")
    
    hashed_password = get_password_hash(user.password)
    new_user = User(email=user.email, name=user.name, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": "회원가입이 완료되었습니다."}

# [API] 로그인 (토큰 발급)
@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """이메일과 비밀번호를 검증한 뒤 JWT 액세스 토큰을 발급합니다."""
    # 폼 데이터의 username 필드로 이메일을 받음
    try:
        email = EmailStr._validate(form_data.username)
    except ValueError:
        raise HTTPException(status_code=400, detail="올바른 이메일 형식이 아닙니다.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록된 계정이 없습니다.")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="비밀번호가 틀렸습니다.")
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# [API] 포트폴리오 생성 및 저장 (로그인 필수)
@app.post("/api/portfolio/save")
async def save_portfolio(data: PortfolioInput, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """로그인 사용자의 기술·프로젝트 정보를 JSON 형태로 저장하고 화면용 데이터를 반환합니다."""
    # 프론트엔드에 돌려줄 포트폴리오 데이터 구조화
    portfolio_content = {
        "title": f"{data.name}의 포트폴리오",
        "intro": f"{data.role} 역할을 맡는 {data.name}의 포트폴리오입니다.",
        "name": data.name,
        "role": data.role,
        "strength": data.strength,
        "tech_stack": [skill.strip() for skill in data.skills.split(",") if skill.strip()],
        "projects": [project.model_dump() for project in data.projects]
    }
    
    # DB 저장 (JSON 문자열로 변환하여 저장)
    new_portfolio = PortfolioDB(
        user_id=current_user.id,
        title=portfolio_content["title"],
        content=json.dumps(portfolio_content, ensure_ascii=False)
    )
    db.add(new_portfolio)
    db.commit()

    return {
        "status": "success", 
        "message": "포트폴리오가 안전하게 저장되었습니다.",
        "portfolio": portfolio_content
    }

@app.get("/api/portfolio/latest")
async def get_latest_portfolio(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """로그인 사용자가 마지막으로 저장한 포트폴리오 한 건을 반환합니다."""
    portfolio = (
        db.query(PortfolioDB)
        .filter(PortfolioDB.user_id == current_user.id)
        .order_by(PortfolioDB.id.desc())
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="저장된 포트폴리오가 없습니다.")
    return json.loads(portfolio.content)
