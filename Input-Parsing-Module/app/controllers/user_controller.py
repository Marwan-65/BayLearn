from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.models.database import get_db
from app.models.db_models import User

from app.models.database import Base

router = APIRouter(prefix="/users", tags=["users"])



class SignupRequest(BaseModel):
    email: str
    name: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str



def _user_response(user: User):
    return {
        "user_id"  : user.id,
        "email"  : user.email,
        "name" : user.name,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    """create a new user acc"""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email = body.email,
        name = body.name,
        password = body.password,  
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_response(user)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """login with email and password """

    user =db.query(User).filter(User.email == body.email).first()
    if not user or user.password != body.password:

        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _user_response(user)