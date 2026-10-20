from decimal import Decimal

from app.core.money import money


def outstanding(amount: Decimal, payments: list[Decimal]) -> Decimal:
    paid = sum((money(value) for value in payments), Decimal("0.00"))
    return money(amount - paid)


def invoice_status(amount: Decimal, balance: Decimal) -> str:
    if balance <= 0:
        return "paid"
    if balance < amount:
        return "partial"
    return "open"
