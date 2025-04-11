from pydantic import BaseModel, EmailStr, constr, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


class MovieBase(BaseModel):
    title: str
    original_title: Optional[str] = None
    description: Optional[str] = None
    year: int
    rating: Optional[int] = None


class MovieCreate(MovieBase):
    pass


class Movie(MovieBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    username: constr(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_-]+$") = Field(
        ...,
        description="Username must be between 3 and 30 characters and can only contain letters, numbers, hyphens, and underscores",
    )
    email: EmailStr = Field(..., description="Valid email address")
    password: constr(min_length=8) = Field(
        ..., description="Password must be at least 8 characters long"
    )
    turnstileToken: str = Field(..., description="Cloudflare Turnstile token")


class UserResponse(BaseModel):
    username: str
    email: EmailStr
    api_key: str
    monthly_request_limit: Optional[int] = 1000  # Месячный лимит
    monthly_requests_remaining: Optional[int] = 1000  # Оставшиеся запросы в месяц
    next_reset_date: Optional[str] = None  # Дата следующего сброса лимита

    class Config:
        from_attributes = True


class APIStats(BaseModel):
    total_requests: int
    requests_today: int
    remaining_requests: int
    daily_limit: int


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


class StatusResponse(BaseModel):
    status: str = "ok"
    request_count: int
    uptime: str  # Добавлено поле uptime
