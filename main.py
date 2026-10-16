"""FastAPI application for managing student records in SQLite."""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Path as FastAPIPath, Query, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "students.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    course TEXT,
    address TEXT,
    enrollment_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_students_name ON students(name);
CREATE INDEX IF NOT EXISTS idx_students_course ON students(course);
"""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection and always close it."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(database_path), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database(database_path: Path) -> None:
    with connection(database_path) as db:
        db.executescript(SCHEMA)


class StudentFields(BaseModel):
    """Fields shared by student creation and full replacement."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120, examples=["Aarav Sharma"])
    date_of_birth: date = Field(examples=["2006-04-15"])
    email: EmailStr | None = Field(default=None, examples=["aarav@example.com"])
    phone: str | None = Field(default=None, min_length=3, max_length=30, examples=["+91 98765 43210"])
    course: str | None = Field(default=None, max_length=120, examples=["Computer Science"])
    address: str | None = Field(default=None, max_length=250)
    enrollment_date: date | None = Field(default=None, examples=["2025-06-01"])

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("phone")
    @classmethod
    def blank_phone_becomes_missing(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) < 3:
            raise ValueError("phone must contain at least 3 characters")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def birth_date_cannot_be_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def require_contact_information(self) -> "StudentFields":
        if not self.email and not self.phone:
            raise ValueError("provide at least one contact method: email or phone")
        return self


class StudentCreate(StudentFields):
    """Validated request body for creating or replacing a student."""


class StudentPatch(BaseModel):
    """Partial update body; explicitly supplied nulls clear optional fields."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    date_of_birth: date | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    course: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=250)
    enrollment_date: date | None = None

    @field_validator("name")
    @classmethod
    def patch_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("phone")
    @classmethod
    def patch_phone_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("phone must not be blank; use null to clear it")
        if len(value) < 3:
            raise ValueError("phone must contain at least 3 characters")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def patch_birth_date_cannot_be_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "StudentPatch":
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        if "date_of_birth" in self.model_fields_set and self.date_of_birth is None:
            raise ValueError("date_of_birth cannot be null")
        return self


class StudentRead(BaseModel):
    """Student record returned by the API."""

    student_id: int
    name: str
    date_of_birth: date
    email: EmailStr | None
    phone: str | None
    course: str | None
    address: str | None
    enrollment_date: date | None
    created_at: datetime
    updated_at: datetime


def serialize_student(row: sqlite3.Row) -> dict[str, object]:
    """Convert SQLite date strings to values suitable for response validation."""
    result: dict[str, object] = dict(row)
    result["date_of_birth"] = date.fromisoformat(str(result["date_of_birth"]))
    if result["enrollment_date"] is not None:
        result["enrollment_date"] = date.fromisoformat(str(result["enrollment_date"]))
    result["created_at"] = datetime.fromisoformat(str(result["created_at"]))
    result["updated_at"] = datetime.fromisoformat(str(result["updated_at"]))
    return result


def as_database_values(student: StudentFields) -> dict[str, object]:
    data = student.model_dump()
    data["date_of_birth"] = student.date_of_birth.isoformat()
    data["enrollment_date"] = (
        student.enrollment_date.isoformat() if student.enrollment_date else None
    )
    if student.email is not None:
        data["email"] = str(student.email)
    return data


def create_app(database_path: str | Path | None = None) -> FastAPI:
    """Create the API app; accepts a custom SQLite path for tests."""
    resolved_path = Path(
        database_path or os.environ.get("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    ).expanduser().resolve()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database(resolved_path)
        yield

    app = FastAPI(
        title="Student CRUD API",
        description=(
            "A small FastAPI + SQLite backend for student records. "
            "Use only dummy records when demonstrating the API."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.database_path = resolved_path

    @app.get("/", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"message": "Student CRUD API is running", "docs": "/docs"}

    @app.post(
        "/students",
        response_model=StudentRead,
        status_code=status.HTTP_201_CREATED,
        tags=["students"],
    )
    def create_student(student: StudentCreate) -> StudentRead:
        data = as_database_values(student)
        now = utc_now()
        with connection(resolved_path) as db:
            cursor = db.execute(
                """
                INSERT INTO students (
                    name, date_of_birth, email, phone, course, address,
                    enrollment_date, created_at, updated_at
                ) VALUES (
                    :name, :date_of_birth, :email, :phone, :course, :address,
                    :enrollment_date, :created_at, :updated_at
                )
                """,
                {**data, "created_at": now, "updated_at": now},
            )
            row = db.execute(
                "SELECT * FROM students WHERE student_id = ?", (cursor.lastrowid,)
            ).fetchone()
        return StudentRead.model_validate(serialize_student(row))

    @app.get("/students", response_model=list[StudentRead], tags=["students"])
    def list_students(
        q: str | None = Query(default=None, min_length=1, description="Search name, email, or phone"),
        course: str | None = Query(default=None, min_length=1),
        date_of_birth_after: date | None = None,
        date_of_birth_before: date | None = None,
        limit: int = Query(default=100, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[StudentRead]:
        if (
            date_of_birth_after
            and date_of_birth_before
            and date_of_birth_after > date_of_birth_before
        ):
            raise HTTPException(
                status_code=422,
                detail="date_of_birth_after must be on or before date_of_birth_before",
            )

        clauses: list[str] = []
        parameters: list[object] = []
        if q:
            pattern = f"%{q.strip()}%"
            clauses.append("(name LIKE ? OR email LIKE ? OR phone LIKE ?)")
            parameters.extend([pattern, pattern, pattern])
        if course:
            clauses.append("course = ?")
            parameters.append(course.strip())
        if date_of_birth_after:
            clauses.append("date_of_birth > ?")
            parameters.append(date_of_birth_after.isoformat())
        if date_of_birth_before:
            clauses.append("date_of_birth < ?")
            parameters.append(date_of_birth_before.isoformat())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connection(resolved_path) as db:
            rows = db.execute(
                f"""
                SELECT * FROM students {where}
                ORDER BY student_id ASC
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
        return [
            StudentRead.model_validate(serialize_student(row))
            for row in rows
        ]

    @app.get(
        "/students/{student_id}",
        response_model=StudentRead,
        tags=["students"],
    )
    def get_student(student_id: int = FastAPIPath(..., gt=0)) -> StudentRead:
        with connection(resolved_path) as db:
            row = db.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Student not found")
        return StudentRead.model_validate(serialize_student(row))

    @app.put(
        "/students/{student_id}",
        response_model=StudentRead,
        tags=["students"],
    )
    def replace_student(student_id: int, student: StudentCreate) -> StudentRead:
        if student_id < 1:
            raise HTTPException(status_code=422, detail="student_id must be greater than 0")
        data = as_database_values(student)
        with connection(resolved_path) as db:
            result = db.execute(
                """
                UPDATE students SET
                    name = :name,
                    date_of_birth = :date_of_birth,
                    email = :email,
                    phone = :phone,
                    course = :course,
                    address = :address,
                    enrollment_date = :enrollment_date,
                    updated_at = :updated_at
                WHERE student_id = :student_id
                """,
                {**data, "updated_at": utc_now(), "student_id": student_id},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Student not found")
            row = db.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
        return StudentRead.model_validate(serialize_student(row))

    @app.patch(
        "/students/{student_id}",
        response_model=StudentRead,
        tags=["students"],
    )
    def update_student(student_id: int, patch: StudentPatch) -> StudentRead:
        if student_id < 1:
            raise HTTPException(status_code=422, detail="student_id must be greater than 0")
        changes = patch.model_dump(exclude_unset=True)
        with connection(resolved_path) as db:
            current = db.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Student not found")

            merged = dict(current)
            merged.update(changes)
            merged["date_of_birth"] = date.fromisoformat(str(merged["date_of_birth"]))
            if merged["enrollment_date"] is not None:
                merged["enrollment_date"] = date.fromisoformat(
                    str(merged["enrollment_date"])
                )
            try:
                validated = StudentCreate.model_validate(merged)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            data = as_database_values(validated)
            db.execute(
                """
                UPDATE students SET
                    name = :name,
                    date_of_birth = :date_of_birth,
                    email = :email,
                    phone = :phone,
                    course = :course,
                    address = :address,
                    enrollment_date = :enrollment_date,
                    updated_at = :updated_at
                WHERE student_id = :student_id
                """,
                {**data, "updated_at": utc_now(), "student_id": student_id},
            )
            row = db.execute(
                "SELECT * FROM students WHERE student_id = ?", (student_id,)
            ).fetchone()
        return StudentRead.model_validate(serialize_student(row))

    @app.delete(
        "/students/{student_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["students"],
    )
    def delete_student(student_id: int) -> Response:
        if student_id < 1:
            raise HTTPException(status_code=422, detail="student_id must be greater than 0")
        with connection(resolved_path) as db:
            result = db.execute(
                "DELETE FROM students WHERE student_id = ?", (student_id,)
            )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
