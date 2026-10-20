from app.core.pagination import paginate


def test_paginate_returns_the_requested_slice() -> None:
    page = paginate(list(range(25)), page=2, page_size=10)
    assert page.items == list(range(10, 20))
    assert page.page == 2
    assert page.page_size == 10
    assert page.total == 25


def test_paginate_past_the_end_is_empty() -> None:
    page = paginate(list(range(3)), page=2, page_size=10)
    assert page.items == []
    assert page.total == 3
