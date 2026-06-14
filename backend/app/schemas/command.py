from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Stroke(BaseModel):
    color: str | None = Field(default=None)
    width: float | None = Field(default=None, ge=0)


class Size(BaseModel):
    width: float | None = Field(default=None, ge=0)
    height: float | None = Field(default=None, ge=0)
    relative: bool = True


class Position(BaseModel):
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    anchor: Literal[
        "top-left",
        "top",
        "top-right",
        "center-left",
        "center",
        "center-right",
        "bottom-left",
        "bottom",
        "bottom-right",
    ] | None = None


class Command(BaseModel):
    action: Literal["draw", "undo", "clear", "save"]
    shape: Literal["circle", "rect", "triangle", "line", "text", "free"] | None = None
    position: Position | None = None
    size: Size | None = None
    color: str | None = None
    stroke: Stroke | None = None
    fill: str | None = None
    text: str | None = None
    comment: str | None = None

    @field_validator("color", "fill")
    @classmethod
    def normalize_color(cls, v: str | None) -> str | None:
        if not v:
            return v
        return v.strip()
