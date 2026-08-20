import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "social-earners-development-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://localhost/social_earners"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
