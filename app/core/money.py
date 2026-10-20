from decimal import Decimal

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWOPLACES)


def money_str(value: Decimal) -> str:
    return format(money(value), "f")
