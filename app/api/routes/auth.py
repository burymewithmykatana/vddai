from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _duplicate_email_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A user with this email already exists.",
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(select(User).where(User.email == user_in.email))

    if existing_user:
        raise _duplicate_email_conflict()

    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing_user = db.scalar(select(User).where(User.email == user_in.email))
        if existing_user is not None:
            raise _duplicate_email_conflict() from exc
        raise
    db.refresh(user)

    return user


@router.post("/login", response_model=Token)
def login_user(
    login_data: UserLogin,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == login_data.email))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    access_token = create_access_token(subject=user.id)

    return Token(access_token=access_token)
