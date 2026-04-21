import re

DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
        "throwaway.email", "yopmail.com", "sharklasers.com", "spam4.me",
        "trashmail.com", "dispostable.com",
    }
)

PHONE_RE = re.compile(r"^\+?[\d\s\-().]{8,20}$")
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> list[str]:
    errors: list[str] = []
    if not email:
        errors.append("Email is required")
        return errors
    if not EMAIL_RE.match(email):
        errors.append(f"Invalid email format: {email}")
    domain = email.split("@")[-1].lower()
    if domain in DISPOSABLE_DOMAINS:
        errors.append(f"Disposable email domain not allowed: {domain}")
    return errors


def validate_phone(phone: str | None) -> list[str]:
    if not phone:
        return []
    cleaned = phone.strip()
    if not PHONE_RE.match(cleaned):
        return [f"Invalid phone format: {cleaned}"]
    return []


def validate_name(name: str) -> list[str]:
    errors: list[str] = []
    if not name or not name.strip():
        errors.append("Name is required")
    elif len(name.strip()) < 2:
        errors.append("Name must have at least 2 characters")
    elif len(name) > 255:
        errors.append("Name must not exceed 255 characters")
    return errors


def validate_lead(lead_data: dict) -> list[str]:
    """Run all business rules and return a list of validation error messages."""
    errors: list[str] = []
    errors.extend(validate_name(lead_data.get("name", "")))
    errors.extend(validate_email(lead_data.get("email", "")))
    errors.extend(validate_phone(lead_data.get("phone")))
    return errors
