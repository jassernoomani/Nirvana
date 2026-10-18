from pydantic import BaseModel, ConfigDict, Field, field_validator  # type: ignore[reportMissingImports]


class MenuItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price: float = Field(gt=0)
    category: str = Field(min_length=1, max_length=50)
    is_available: bool = True
    preparation_minutes: int = Field(default=15, ge=1, le=240)
    is_vegetarian: bool = False
    image_url: str | None = Field(default=None, pattern=r"^/assets/dishes/[a-zA-Z0-9_-]+\.(?:png|jpg|webp)$")


class MenuItem(MenuItemCreate):
    id: int


class MenuItemPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", allow_inf_nan=False)
    name: str = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    price: float = Field(default=None, gt=0)
    category: str = Field(default=None, min_length=1, max_length=50)
    is_available: bool = Field(default=None)
    preparation_minutes: int = Field(default=None, ge=1, le=240)
    is_vegetarian: bool = Field(default=None)
    image_url: str | None = Field(default=None, pattern=r"^/assets/dishes/[a-zA-Z0-9_-]+\.(?:png|jpg|webp)$")


class MenuPage(BaseModel):
    items: list[MenuItem]
    total: int
    page: int
    page_size: int


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    # Unknown fields such as "role" are ignored: public sign-up always creates a customer.
    model_config = ConfigDict(extra="ignore")
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    # Trim email and name (never the password) before the length and format checks.
    @field_validator("email", "full_name", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class User(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_vegetarian: bool
