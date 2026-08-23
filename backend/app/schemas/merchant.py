import uuid

from pydantic import BaseModel, Field


class MerchantAccountCreate(BaseModel):
    business_name: str = Field(min_length=1)
    razorpay_key_id: str = Field(min_length=1, description="Public Razorpay key ID only — never the secret")
    is_test_mode: bool = True


class MerchantAccountOut(BaseModel):
    id: uuid.UUID
    business_name: str
    razorpay_key_id: str
    is_test_mode: bool

    class Config:
        from_attributes = True
