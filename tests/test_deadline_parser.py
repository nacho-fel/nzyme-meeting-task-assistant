from datetime import date

from app.services.deadline_parser import normalise_deadline


def test_engineering_deadlines():
    meeting = date(2025, 6, 10)
    assert normalise_deadline("before Friday", meeting) == date(2025, 6, 13)
    assert normalise_deadline("this afternoon", meeting) == date(2025, 6, 10)
    assert normalise_deadline("next Wednesday", meeting) == date(2025, 6, 18)
    assert normalise_deadline("tomorrow probably", meeting) == date(2025, 6, 11)
    assert normalise_deadline("before the product review on the 24th", meeting) == date(2025, 6, 24)
    assert normalise_deadline("before the end of the month", meeting) == date(2025, 6, 30)


def test_pricing_deadlines():
    meeting = date(2025, 6, 11)
    assert normalise_deadline("before Thursday", meeting) == date(2025, 6, 12)
    assert normalise_deadline("Monday EOD", meeting) == date(2025, 6, 16)
    assert normalise_deadline("Tuesday", meeting) == date(2025, 6, 17)
    assert normalise_deadline("today or tomorrow", meeting) == date(2025, 6, 12)
    assert normalise_deadline("end of July", meeting) == date(2025, 7, 31)
