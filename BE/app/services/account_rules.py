"""
What a sign-in may look like: the password, username and email rules applied
wherever an account is created or changed (the users screen, setup, a person
changing their own password).

An approver's password binds their signature to a quality record, so it is not
allowed to be empty, a single repeated letter, or eight lower-case letters.
"""
from __future__ import annotations

import re
from typing import Optional

MIN_LENGTH = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,49}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def password_problem(password: Optional[str]) -> Optional[str]:
    """Why this password is not acceptable, or None."""
    password = password or ""
    if len(password) < MIN_LENGTH:
        return f"The password must be at least {MIN_LENGTH} characters."
    if len(set(password)) < 4:
        return "The password is too simple: use more different characters."
    kinds = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if kinds < 3:
        return ("The password must mix at least three of: lower-case letters, upper-case letters, "
                "digits and symbols.")
    return None


def check_password(password: Optional[str]) -> Optional[str]:
    """For a pydantic validator: the password, or a ValueError with the reason."""
    if password is None:
        return None
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    return password


def check_username(username: Optional[str]) -> Optional[str]:
    if username is None:
        return None
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise ValueError("A username is 2-50 letters, digits, dots, dashes or underscores, starting with a letter or digit.")
    return username


def check_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    email = email.strip()
    if not EMAIL_RE.match(email):
        raise ValueError("That is not an email address.")
    return email
