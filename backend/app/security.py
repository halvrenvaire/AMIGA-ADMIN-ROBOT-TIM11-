import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def password_problem(password: str, email: str) -> str | None:
    """Aturan password baru. Mengembalikan alasan penolakan, atau None bila boleh dipakai."""
    if len(password) < 8:
        return "Password minimal 8 karakter."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password harus berisi huruf dan angka."
    if password.lower() == email.lower() or password.lower() == email.split("@")[0].lower():
        return "Password tidak boleh sama dengan email."
    return None
