from tortoise import fields
from tortoise.models import Model
from datetime import datetime


class User(Model):
    id = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(unique=True)
    username = fields.CharField(max_length=100, null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    exchange_accounts: fields.ReverseRelation["ExchangeAccount"]
    subscriptions: fields.ReverseRelation["Subscription"]
    
    api_credentials: fields.ReverseRelation["UserAPI"]

    def __str__(self):
        return f"User({self.telegram_id})"


class ExchangeAccount(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="exchange_accounts")
    exchange_name = fields.CharField(max_length=50)  # e.g., "bybit", "bitunix"
    api_key = fields.CharField(max_length=128)
    api_secret = fields.CharField(max_length=128)
    is_real = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.exchange_name} ({'Real' if self.is_real else 'Test'})"


class Subscription(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="subscriptions")
    is_paid = fields.BooleanField(default=False)
    start_date = fields.DatetimeField(default=datetime.utcnow)
    end_date = fields.DatetimeField(null=True)

    def __str__(self):
        return f"Subscription({self.user_id})"

    
class UserAPI(Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="api_credentials")
    exchange = fields.CharField(max_length=32)  # bybit یا bitunix
    api_key = fields.CharField(max_length=256)
    api_secret = fields.CharField(max_length=256)
    created_at = fields.DatetimeField(auto_now_add=True)
