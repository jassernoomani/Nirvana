from pydantic import BaseModel, ConfigDict, Field  # type: ignore[reportMissingImports]


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
