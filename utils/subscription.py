from datetime import datetime

async def has_active_subscription(user) -> bool:
    subs = await user.subscriptions.all().order_by("-start_date")
    if not subs:
        return False

    latest = subs[0]
    if not latest.is_paid:
        return False

    if latest.end_date and latest.end_date < datetime.utcnow():
        return False

    return True
