from app.db.session import SessionLocal
from app.models.user import User


def seed_test_user() -> None:
    db = SessionLocal()

    try:
        existing_user = (
            db.query(User)
            .filter(User.email == "test@example.com")
            .first()
        )

        if existing_user is not None:
            print(f"Test user already exists with id={existing_user.id}")
            return

        user = User(
            email="test@example.com",
            hashed_password="not-a-real-password",
            full_name="Test User",
            is_active=True,
            is_admin=False,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"Created test user with id={user.id}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_test_user()