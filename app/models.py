from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_activated = db.Column(db.Boolean, default=False, nullable=False)

    deposit_balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    task_balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    referral_balance = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    referral_code = db.Column(db.String(30), unique=True, nullable=False)
    referred_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Deposit(db.Model):
    __tablename__ = "deposits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    bank_used = db.Column(db.String(120), nullable=False)
    depositor_name = db.Column(db.String(120), nullable=False)
    screenshot = db.Column(db.String(500), nullable=True)

    status = db.Column(db.String(20), default="pending", nullable=False)
    admin_reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    user = db.relationship("User", backref="deposits")


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    task_type = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    target_url = db.Column(db.String(500), nullable=True)

    total_cost = db.Column(db.Numeric(12, 2), nullable=False)
    worker_reward = db.Column(db.Numeric(12, 2), nullable=False)
    website_fee = db.Column(db.Numeric(12, 2), nullable=False)
    number_needed = db.Column(db.Integer, nullable=False, default=1)

    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    creator = db.relationship("User", backref="created_tasks")


class TaskSubmission(db.Model):
    __tablename__ = "task_submissions"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    note = db.Column(db.Text, nullable=True)
    screenshot = db.Column(db.String(500), nullable=True)

    status = db.Column(db.String(20), default="pending", nullable=False)
    rejection_reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    task = db.relationship("Task", backref="submissions")
    worker = db.relationship("User", backref="task_submissions")


class Withdrawal(db.Model):
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    wallet_type = db.Column(db.String(30), nullable=False)

    bank_name = db.Column(db.String(120), nullable=False)
    account_number = db.Column(db.String(30), nullable=False)
    account_name = db.Column(db.String(120), nullable=False)

    status = db.Column(db.String(20), default="pending", nullable=False)
    admin_reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref="withdrawals")


class AirtimePurchase(db.Model):
    __tablename__ = "airtime_purchases"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    network = db.Column(db.String(30), nullable=False)
    phone_number = db.Column(db.String(30), nullable=False)

    wallet_type = db.Column(db.String(30), default="task", nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref="airtime_purchases")
