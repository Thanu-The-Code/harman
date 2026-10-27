"""Admin-managed departments used when creating and assigning users."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Department, User
from ..services.auth_service import require_admin_flexible

router = APIRouter()


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@router.get("")
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """List departments for the admin's user-creation form."""
    departments = (
        db.query(Department)
        .order_by(func.lower(Department.name), Department.id)
        .all()
    )
    return {
        "departments": [
            {"id": department.id, "name": department.name}
            for department in departments
        ],
        "total": len(departments),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Create a department that can be selected for new users."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Department name cannot be blank.")

    existing = (
        db.query(Department)
        .filter(func.lower(Department.name) == name.lower())
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this name already exists.",
        )

    department = Department(name=name)
    db.add(department)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this name already exists.",
        ) from exc
    db.refresh(department)
    return {"id": department.id, "name": department.name}


@router.delete("/{department_id}")
def delete_department(
    department_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    """Delete an unused department."""
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )
    if department.users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reassign or remove all users from this department before deleting it.",
        )

    db.delete(department)
    db.commit()
    return {"message": "Department deleted successfully."}
