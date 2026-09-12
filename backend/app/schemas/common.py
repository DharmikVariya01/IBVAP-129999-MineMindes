"""Common Pydantic schemas for pagination and standardized responses."""

from typing import Generic, List, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized paginated list response schema."""

    items: List[T] = Field(..., description="List of items for the requested page.")
    total: int = Field(..., ge=0, description="Total number of items matching filter criteria.")
    page: int = Field(..., ge=1, description="Current page number (1-indexed).")
    page_size: int = Field(..., ge=1, description="Number of items per page.")
    total_pages: int = Field(..., ge=0, description="Total number of pages available.")
