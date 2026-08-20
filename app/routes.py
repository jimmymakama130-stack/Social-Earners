from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
from flask_login import login_required, current_user

from app import db
from app.models import User, Deposit, Withdrawal, AirtimePurchase, TaskSubmission, Task, TaskSubmission

main = Blueprint("main", __name__)


@main.route("/")
def home():
    return render_template("home.html")


@main.route("/dashboard")
@login_required
def dashboard():
    total_balance = (
        Decimal(current_user.deposit_balance)
        + Decimal(current_user.task_balance)
        + Decimal(current_user.referral_balance)
    )

    activities = []

    for item in current_user.deposits:
        activities.append({
            "type": "Deposit",
            "description": f"Deposit ₦{Decimal(item.amount):,.2f}",
            "status": item.status,
            "created_at": item.created_at
        })

    for item in current_user.withdrawals:
        activities.append({
            "type": "Withdrawal",
            "description": f"Withdrawal ₦{Decimal(item.amount):,.2f} from {item.wallet_type.title()} wallet",
            "status": item.status,
            "created_at": item.created_at
        })

    for item in current_user.airtime_purchases:
        activities.append({
            "type": "Airtime",
            "description": f"Airtime ₦{Decimal(item.amount):,.2f} ({item.network})",
            "status": item.status,
            "created_at": item.created_at
        })

    for item in current_user.task_submissions:
        activities.append({
            "type": "Task",
            "description": f"Task submission #{item.id}",
            "status": item.status,
            "created_at": item.created_at
        })

    activities.sort(
        key=lambda x: x["created_at"] or 0,
        reverse=True
    )

    activities = activities[:8]

    return render_template(
        "user/dashboard.html",
        total_balance=total_balance,
        activities=activities
    )


@main.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        try:
            amount = Decimal(request.form.get("amount", "0"))
        except Exception:
            flash("Enter a valid deposit amount.", "error")
            return redirect(url_for("main.deposit"))

        bank_used = request.form.get("bank_used", "").strip()
        depositor_name = request.form.get("depositor_name", "").strip()

        if amount <= 0:
            flash("Deposit amount must be greater than zero.", "error")
        elif not bank_used or not depositor_name:
            flash("Please complete all required fields.", "error")
        else:
            record = Deposit(
                user_id=current_user.id,
                amount=amount,
                bank_used=bank_used,
                depositor_name=depositor_name
            )

            db.session.add(record)
            db.session.commit()

            flash("Deposit submitted for admin approval.", "success")

        return redirect(url_for("main.deposit"))

    deposits = Deposit.query.filter_by(
        user_id=current_user.id
    ).order_by(Deposit.created_at.desc()).all()

    return render_template(
        "user/deposit.html",
        deposits=deposits
    )


@main.route("/tasks")
@login_required
def tasks():
    from app.models import Task

    if not current_user.is_activated:
        flash("Activate your account to access tasks.", "error")
        return redirect(url_for("main.activate_account"))

    available_tasks = Task.query.filter(
        Task.status == "active",
        Task.creator_id != current_user.id,
        ~Task.submissions.any(
            db.and_(
                TaskSubmission.worker_id == current_user.id,
                TaskSubmission.status.in_(["pending", "approved"])
            )
        )
    ).order_by(
        Task.created_at.desc()
    ).all()

    rejected_submissions = {
        s.task_id: s for s in TaskSubmission.query.filter_by(
            worker_id=current_user.id,
            status="rejected"
        ).order_by(TaskSubmission.created_at.desc()).all()
    }

    return render_template(
        "user/tasks.html",
        tasks=available_tasks,
        rejected_submissions=rejected_submissions
    )


@main.route("/my-tasks")
@login_required
def my_tasks():
    from app.models import Task

    my_tasks = Task.query.filter_by(
        creator_id=current_user.id
    ).order_by(
        Task.created_at.desc()
    ).all()

    return render_template(
        "user/my_tasks.html",
        tasks=my_tasks
    )


@main.route("/create-task", methods=["GET", "POST"])
@login_required
def create_task():
    from app.models import Task
    from app.task_types import TASK_TYPES

    if not current_user.is_activated:
        flash("Activate your account before creating tasks.", "error")
        return redirect(url_for("main.activate_account"))

    if request.method == "POST":
        task_type = request.form.get("task_type", "").strip()
        title = request.form.get("title", "").strip()
        instructions = request.form.get("instructions", "").strip()
        target_url = request.form.get("target_url", "").strip()

        if task_type not in TASK_TYPES:
            flash("Invalid task type.", "error")
            return redirect(url_for("main.create_task"))

        if not title or not instructions:
            flash("Complete the task details.", "error")
            return redirect(url_for("main.create_task"))

        try:
            number_needed = int(request.form.get("number_needed", "0"))
        except (TypeError, ValueError):
            number_needed = 0

        if number_needed < 5:
            flash("Number needed must be at least 5.", "error")
            return redirect(url_for("main.create_task"))

        _, reward, fee = TASK_TYPES[task_type]

        total = Decimal(str(number_needed)) * (
            Decimal(str(reward)) + Decimal(str(fee))
        )

        if Decimal(current_user.deposit_balance) < total:
            flash(
                f"Insufficient deposit balance. You need ₦{total:,.2f}.",
                "error"
            )
            return redirect(url_for("main.create_task"))

        task = Task(
            creator_id=current_user.id,
            task_type=task_type,
            title=title,
            instructions=instructions,
            target_url=target_url,
            total_cost=total,
            worker_reward=reward,
            website_fee=fee,
            number_needed=number_needed
        )

        current_user.deposit_balance = (
            Decimal(current_user.deposit_balance) - total
        )

        db.session.add(task)
        db.session.commit()

        flash("Task created successfully.", "success")
        return redirect(url_for("main.tasks"))

    return render_template(
        "user/create_task.html",
        task_types=TASK_TYPES
    )




@main.route("/task/<int:task_id>", methods=["GET", "POST"])
@login_required
def task_details(task_id):
    task = db.session.get(Task, task_id)

    if not task or task.status != "active":
        flash("Task is not available.", "error")
        return redirect(url_for("main.tasks"))

    # A task creator cannot submit their own task.
    if task.creator_id == current_user.id:
        flash("You cannot submit your own task.", "error")
        return redirect(url_for("main.tasks"))

    if request.method == "POST":
        screenshot = request.files.get("screenshot")
        note = request.form.get("note", "").strip()

        if not screenshot or not screenshot.filename:
            flash("Please upload a screenshot.", "error")
            return redirect(url_for("main.task_details", task_id=task.id))

        # Prevent duplicate pending/approved submissions for the same worker/task.
        existing = TaskSubmission.query.filter(
            TaskSubmission.task_id == task.id,
            TaskSubmission.worker_id == current_user.id,
            TaskSubmission.status.in_(["pending", "approved"])
        ).first()

        if existing:
            flash("You have already submitted this task.", "error")
            return redirect(url_for("main.tasks"))

        upload_dir = Path("app/static/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        original = secure_filename(screenshot.filename)

        if not original:
            flash("Invalid screenshot file.", "error")
            return redirect(url_for("main.task_details", task_id=task.id))

        extension = Path(original).suffix.lower()

        allowed = {".png", ".jpg", ".jpeg", ".webp"}

        if extension not in allowed:
            flash("Only PNG, JPG, JPEG and WEBP screenshots are allowed.", "error")
            return redirect(url_for("main.task_details", task_id=task.id))

        filename = f"task_{task.id}_{current_user.id}_{uuid.uuid4().hex}{extension}"
        file_path = upload_dir / filename
        screenshot.save(file_path)

        submission = TaskSubmission(
            task_id=task.id,
            worker_id=current_user.id,
            note=note,
            screenshot=f"uploads/{filename}",
            status="pending"
        )

        db.session.add(submission)
        db.session.commit()

        flash("Task submitted successfully. Waiting for the task creator to review it.", "success")
        return redirect(url_for("main.tasks"))

    return render_template("user/task_details.html", task=task)


@main.route("/my-task/<int:task_id>/submissions")
@login_required
def task_submissions(task_id):
    task = db.session.get(Task, task_id)

    if not task:
        flash("Task not found.", "error")
        return redirect(url_for("main.tasks"))

    # ONLY the creator can view submissions.
    if task.creator_id != current_user.id:
        flash("You can only review submissions for your own tasks.", "error")
        return redirect(url_for("main.tasks"))

    submissions = TaskSubmission.query.filter_by(
        task_id=task.id,
        status="pending"
    ).order_by(
        TaskSubmission.created_at.desc()
    ).all()

    return render_template(
        "user/task_submissions.html",
        task=task,
        submissions=submissions
    )


@main.route("/my-task/submission/<int:submission_id>/approve", methods=["POST"])
@login_required
def approve_task_submission(submission_id):
    # Lock the submission row so two approval requests cannot pay it twice.
    submission = db.session.execute(
        db.select(TaskSubmission)
        .where(TaskSubmission.id == submission_id)
        .with_for_update()
    ).scalar_one_or_none()

    if not submission:
        flash("Submission not found.", "error")
        return redirect(url_for("main.tasks"))

    task = db.session.get(Task, submission.task_id)

    if not task or task.creator_id != current_user.id:
        flash("You are not allowed to review this submission.", "error")
        return redirect(url_for("main.tasks"))

    if submission.status != "pending":
        flash("This submission has already been processed.", "error")
        return redirect(url_for("main.task_submissions", task_id=task.id))

    worker = db.session.get(User, submission.worker_id)

    if not worker:
        flash("Worker not found.", "error")
        return redirect(url_for("main.task_submissions", task_id=task.id))

    # Pay the worker from the task's reserved worker reward.
    worker.task_balance = (
        Decimal(worker.task_balance) + Decimal(task.worker_reward)
    )

    submission.status = "approved"

    # Count approved submissions.
    approved_count = TaskSubmission.query.filter_by(
        task_id=task.id,
        status="approved"
    ).count()

    # Include this approval.
    approved_count += 1

    if approved_count >= task.number_needed:
        task.status = "completed"

    db.session.commit()

    flash("Submission approved and worker reward added.", "success")
    return redirect(url_for("main.task_submissions", task_id=task.id))


@main.route("/my-task/submission/<int:submission_id>/reject", methods=["POST"])
@login_required
def reject_task_submission(submission_id):
    submission = db.session.get(TaskSubmission, submission_id)

    if not submission:
        flash("Submission not found.", "error")
        return redirect(url_for("main.tasks"))

    task = db.session.get(Task, submission.task_id)

    if not task or task.creator_id != current_user.id:
        flash("You are not allowed to review this submission.", "error")
        return redirect(url_for("main.tasks"))

    if submission.status != "pending":
        flash("This submission has already been processed.", "error")
        return redirect(url_for("main.task_submissions", task_id=task.id))

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a rejection reason.", "error")
        return redirect(url_for("main.task_submissions", task_id=task.id))

    submission.status = "rejected"
    submission.rejection_reason = reason

    db.session.commit()

    flash("Submission rejected. The screenshot has been kept.", "success")
    return redirect(url_for("main.task_submissions", task_id=task.id))


@main.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    if request.method == "POST":
        try:
            amount = Decimal(request.form.get("amount", "0"))
        except Exception:
            flash("Enter a valid amount.", "error")
            return redirect(url_for("main.withdraw"))

        wallet_type = request.form.get("wallet_type", "task")
        bank_name = request.form.get("bank_name", "").strip()
        account_number = request.form.get("account_number", "").strip()
        account_name = request.form.get("account_name", "").strip()

        minimum = Decimal("400") if wallet_type == "task" else Decimal("300")

        balance = (
            Decimal(current_user.task_balance)
            if wallet_type == "task"
            else Decimal(current_user.referral_balance)
        )

        if amount < minimum:
            flash(
                f"Minimum withdrawal is ₦{minimum:,.0f}.",
                "error"
            )
        elif amount > balance:
            flash("Insufficient balance.", "error")
        elif not bank_name or not account_number or not account_name:
            flash("Complete your bank details.", "error")
        else:
            withdrawal = Withdrawal(
                user_id=current_user.id,
                amount=amount,
                wallet_type=wallet_type,
                bank_name=bank_name,
                account_number=account_number,
                account_name=account_name
            )

            if wallet_type == "task":
                current_user.task_balance = (
                    Decimal(current_user.task_balance) - amount
                )
            else:
                current_user.referral_balance = (
                    Decimal(current_user.referral_balance) - amount
                )

            db.session.add(withdrawal)
            db.session.commit()

            flash("Withdrawal submitted for admin approval.", "success")

        return redirect(url_for("main.withdraw"))

    withdrawals = Withdrawal.query.filter_by(
        user_id=current_user.id
    ).order_by(Withdrawal.created_at.desc()).all()

    return render_template(
        "user/withdraw.html",
        withdrawals=withdrawals
    )


@main.route("/airtime", methods=["GET", "POST"])
@login_required
def airtime():
    if request.method == "POST":
        try:
            amount = Decimal(request.form.get("amount", "0"))
        except Exception:
            flash("Enter a valid amount.", "error")
            return redirect(url_for("main.airtime"))

        network = request.form.get("network", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        wallet_type = request.form.get("wallet_type", "task")

        if amount < Decimal("100"):
            flash("Minimum airtime purchase is ₦100.", "error")
        else:
            balance = (
                Decimal(current_user.task_balance)
                if wallet_type == "task"
                else Decimal(current_user.referral_balance)
            )

            if amount > balance:
                flash("Insufficient balance.", "error")
            elif not network or not phone_number:
                flash("Complete all airtime details.", "error")
            else:
                purchase = AirtimePurchase(
                    user_id=current_user.id,
                    amount=amount,
                    network=network,
                    phone_number=phone_number,
                    wallet_type=wallet_type
                )

                if wallet_type == "task":
                    current_user.task_balance = (
                        Decimal(current_user.task_balance) - amount
                    )
                else:
                    current_user.referral_balance = (
                        Decimal(current_user.referral_balance) - amount
                    )

                db.session.add(purchase)
                db.session.commit()

                flash("Airtime request submitted.", "success")

        return redirect(url_for("main.airtime"))

    purchases = AirtimePurchase.query.filter_by(
        user_id=current_user.id
    ).order_by(AirtimePurchase.created_at.desc()).all()

    return render_template(
        "user/airtime.html",
        purchases=purchases
    )



@main.route("/activate", methods=["GET", "POST"])
@login_required
def activate_account():
    if current_user.is_activated:
        flash("Your account is already activated.", "success")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        activation_amount = Decimal("300")

        if Decimal(current_user.deposit_balance) < activation_amount:
            flash(
                "You need at least ₦300 in your deposit balance to activate.",
                "error"
            )
            return redirect(url_for("main.activate_account"))

        current_user.deposit_balance = (
            Decimal(current_user.deposit_balance) - activation_amount
        )

        current_user.is_activated = True

        # One-time activation bonus
        current_user.task_balance = (
            Decimal(current_user.task_balance) + Decimal("100")
        )

        # One-time referral bonus for the person who referred this user.
        if current_user.referred_by:
            referrer = db.session.get(User, current_user.referred_by)

            if referrer:
                referrer.referral_balance = (
                    Decimal(referrer.referral_balance) + Decimal("100")
                )

        db.session.commit()

        flash(
            "Account activated successfully! ₦100 has been added to your task balance.",
            "success"
        )

        return redirect(url_for("main.dashboard"))

    return render_template("user/activate.html")


@main.route("/admin")
@login_required
def admin_dashboard():
    if current_user.username != "jimmy":
        flash("Admin access required.", "error")
        return redirect(url_for("main.dashboard"))
    return render_template("admin/dashboard.html")


@main.route("/admin/deposits")
@login_required
def admin_deposits():
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    deposits = Deposit.query.filter_by(
        status="pending"
    ).order_by(
        Deposit.created_at.desc()
    ).all()

    return render_template(
        "admin/deposits.html",
        deposits=deposits
    )


@main.route("/admin/deposits/<int:deposit_id>/approve", methods=["POST"])
@login_required
def approve_deposit(deposit_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    deposit = db.session.get(Deposit, deposit_id)

    if not deposit:
        flash("Deposit not found.", "error")
        return redirect(url_for("main.admin_deposits"))

    if deposit.status != "pending":
        flash("This deposit has already been processed.", "error")
        return redirect(url_for("main.admin_deposits"))

    user = db.session.get(User, deposit.user_id)

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_deposits"))

    user.deposit_balance = (
        Decimal(user.deposit_balance) + Decimal(deposit.amount)
    )

    deposit.status = "approved"
    deposit.admin_reason = "Deposit approved."

    db.session.commit()

    flash(
        f"Deposit of ₦{Decimal(deposit.amount):,.2f} approved.",
        "success"
    )

    return redirect(url_for("main.admin_deposits"))


@main.route("/admin/deposits/<int:deposit_id>/reject", methods=["POST"])
@login_required
def reject_deposit(deposit_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    deposit = db.session.get(Deposit, deposit_id)

    if not deposit:
        flash("Deposit not found.", "error")
        return redirect(url_for("main.admin_deposits"))

    if deposit.status != "pending":
        flash("This deposit has already been processed.", "error")
        return redirect(url_for("main.admin_deposits"))

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a rejection reason.", "error")
        return redirect(url_for("main.admin_deposits"))

    deposit.status = "rejected"
    deposit.admin_reason = reason

    db.session.commit()

    flash("Deposit rejected. No balance was added.", "success")

    return redirect(url_for("main.admin_deposits"))


@main.route("/admin/withdrawals")
@login_required
def admin_withdrawals():
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    withdrawals = Withdrawal.query.order_by(
        Withdrawal.created_at.desc()
    ).all()

    return render_template(
        "admin/withdrawals.html",
        withdrawals=withdrawals
    )


@main.route("/admin/withdrawals/<int:withdrawal_id>/approve", methods=["POST"])
@login_required
def approve_withdrawal(withdrawal_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    withdrawal = db.session.get(Withdrawal, withdrawal_id)

    if not withdrawal:
        flash("Withdrawal not found.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    if withdrawal.status != "pending":
        flash("This withdrawal has already been processed.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    withdrawal.status = "approved"
    withdrawal.admin_reason = "Withdrawal approved."

    db.session.commit()

    flash(
        f"Withdrawal of ₦{Decimal(withdrawal.amount):,.2f} approved.",
        "success"
    )

    return redirect(url_for("main.admin_withdrawals"))


@main.route("/admin/withdrawals/<int:withdrawal_id>/reject", methods=["POST"])
@login_required
def reject_withdrawal(withdrawal_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    withdrawal = db.session.get(Withdrawal, withdrawal_id)

    if not withdrawal:
        flash("Withdrawal not found.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    if withdrawal.status != "pending":
        flash("This withdrawal has already been processed.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a rejection reason.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    user = db.session.get(User, withdrawal.user_id)

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    amount = Decimal(withdrawal.amount)
    wallet = withdrawal.wallet_type.lower().strip()

    if wallet == "task":
        user.task_balance = Decimal(user.task_balance) + amount
    elif wallet == "referral":
        user.referral_balance = Decimal(user.referral_balance) + amount
    elif wallet == "deposit":
        user.deposit_balance = Decimal(user.deposit_balance) + amount
    else:
        flash("Unknown withdrawal wallet type.", "error")
        return redirect(url_for("main.admin_withdrawals"))

    withdrawal.status = "rejected"
    withdrawal.admin_reason = reason

    db.session.commit()

    flash(
        f"Withdrawal rejected. ₦{amount:,.2f} returned to the user's wallet.",
        "success"
    )

    return redirect(url_for("main.admin_withdrawals"))


@main.route("/admin/users")
@login_required
def admin_users():
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    users = User.query.order_by(User.id.desc()).all()

    return render_template(
        "admin/users.html",
        users=users
    )


@main.route("/admin/users/<int:user_id>/ban", methods=["POST"])
@login_required
def ban_user(user_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    user = db.session.get(User, user_id)

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_users"))

    if user.username == "jimmy":
        flash("The admin account cannot be banned.", "error")
        return redirect(url_for("main.admin_users"))

    user.is_active = False
    db.session.commit()

    flash(f"@{user.username} has been banned.", "success")

    return redirect(url_for("main.admin_users"))


@main.route("/admin/users/<int:user_id>/unban", methods=["POST"])
@login_required
def unban_user(user_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    user = db.session.get(User, user_id)

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_users"))

    user.is_active = True
    db.session.commit()

    flash(f"@{user.username} has been unbanned.", "success")

    return redirect(url_for("main.admin_users"))


@main.route("/admin/tasks")
@login_required
def admin_tasks():
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    from app.models import Task

    tasks = Task.query.order_by(
        Task.created_at.desc()
    ).all()

    return render_template(
        "admin/tasks.html",
        tasks=tasks
    )


@main.route("/admin/airtime")
@login_required
def admin_airtime():
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    purchases = AirtimePurchase.query.order_by(
        AirtimePurchase.created_at.desc()
    ).all()

    return render_template(
        "admin/airtime.html",
        purchases=purchases
    )


@main.route("/admin/airtime/<int:purchase_id>/approve", methods=["POST"])
@login_required
def approve_airtime(purchase_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    purchase = db.session.get(AirtimePurchase, purchase_id)

    if not purchase:
        flash("Airtime purchase not found.", "error")
        return redirect(url_for("main.admin_airtime"))

    if purchase.status != "pending":
        flash("This airtime purchase has already been processed.", "error")
        return redirect(url_for("main.admin_airtime"))

    purchase.status = "approved"
    db.session.commit()

    flash("Airtime purchase approved.", "success")
    return redirect(url_for("main.admin_airtime"))


@main.route("/admin/airtime/<int:purchase_id>/reject", methods=["POST"])
@login_required
def reject_airtime(purchase_id):
    if current_user.username != "jimmy":
        return redirect(url_for("main.dashboard"))

    purchase = db.session.get(AirtimePurchase, purchase_id)

    if not purchase:
        flash("Airtime purchase not found.", "error")
        return redirect(url_for("main.admin_airtime"))

    if purchase.status != "pending":
        flash("This airtime purchase has already been processed.", "error")
        return redirect(url_for("main.admin_airtime"))

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a rejection reason.", "error")
        return redirect(url_for("main.admin_airtime"))

    user = db.session.get(User, purchase.user_id)

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_airtime"))

    amount = Decimal(purchase.amount)
    wallet = purchase.wallet_type.lower().strip()

    if wallet == "task":
        user.task_balance = Decimal(user.task_balance) + amount
    elif wallet == "referral":
        user.referral_balance = Decimal(user.referral_balance) + amount
    else:
        flash("Unknown airtime wallet type.", "error")
        return redirect(url_for("main.admin_airtime"))

    purchase.status = "rejected"

    db.session.commit()

    flash(
        f"Airtime purchase rejected. ₦{amount:,.2f} returned to the user's wallet.",
        "success"
    )

    return redirect(url_for("main.admin_airtime"))

@main.route("/referrals")
@login_required
def referrals():
    return render_template(
        "user/referrals.html",
        referral_code=current_user.referral_code
    )
