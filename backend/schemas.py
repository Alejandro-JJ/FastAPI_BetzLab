"""
Structure of the data that comes in from requests from the API
and goes out from our code in responses.
This is done for data validation
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserRead(BaseModel):
    id: int
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str # it will be hashed before storing

class UserRegister(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None