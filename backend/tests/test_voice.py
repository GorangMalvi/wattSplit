from datetime import date

import pytest

from app.voice import parse_payment

TODAY = date(2026, 10, 7)  # a Wednesday


@pytest.mark.parametrize("said, amount, when, meter", [
    # English
    ("I added 500 rupees today", 500, "2026-10-07", "main"),
    ("I have added 1500 on 5 October", 1500, "2026-10-05", "main"),
    ("DG recharge 300 on 5th October", 300, "2026-10-05", "dg"),
    ("paid rs 2,000 yesterday for the main meter", 2000, "2026-10-06", "main"),
    ("₹750 D.G. on October 2", 750, "2026-10-02", "dg"),
    ("five hundred rupees on 3/10", 500, "2026-10-03", "main"),
    ("one thousand two hundred and fifty rupees", 1250, "2026-10-07", "main"),
    ("fifteen hundred for generator on monday", 1500, "2026-10-05", "dg"),
    ("recharged 2k on the 1st", 2000, "2026-10-01", "main"),
    ("added 400 on 28 september", 400, "2026-09-28", "main"),
    ("I added 600 on 25th", 600, "2026-09-25", "main"),  # the 25th hasn't come yet this month
    ("500/- on 05.10.2026", 500, "2026-10-05", "main"),
    ("added 999.50 on 2026-10-04", 999.5, "2026-10-04", "main"),
    ("added 300 in december", 300, "2026-10-07", "main"),  # month alone isn't a date
    # Hinglish (Latin script)
    ("maine kal paanch sau ka recharge kiya", 500, "2026-10-06", "main"),
    ("aaj DG mein do hazaar dale", 2000, "2026-10-07", "dg"),
    ("dedh hazaar ka recharge 5 tarikh ko", 1500, "2026-10-05", "main"),
    ("dhai sau rupaye parso", 250, "2026-10-05", "main"),
    ("saadhe teen sau ka DG recharge", 350, "2026-10-07", "dg"),
    ("paune do hazaar main meter", 1750, "2026-10-07", "main"),
    ("ek hazaar paanch sau kal", 1500, "2026-10-06", "main"),
    ("maine 800 rupaye somvar ko dale", 800, "2026-10-05", "main"),
    ("aaj DG mai 20 rupaye dale", 20, "2026-10-07", "dg"),  # "mai" = in, not May
    # Hindi (Devanagari)
    ("मैंने कल पांच सौ रुपये का रिचार्ज किया", 500, "2026-10-06", "main"),
    ("आज डीजी में दो हज़ार डाले", 2000, "2026-10-07", "dg"),
    ("५ अक्टूबर को १५०० रुपये", 1500, "2026-10-05", "main"),
    ("डेढ़ हजार परसों", 1500, "2026-10-05", "main"),
])
def test_parse_payment(said, amount, when, meter):
    got = parse_payment(said, TODAY)
    assert (got["amount"], got["date"], got["meter"]) == (amount, when, meter)


def test_nothing_understood():
    got = parse_payment("hello how are you", TODAY)
    assert got["amount"] is None
    assert got["date"] == "2026-10-07" and not got["date_said"]
    assert got["meter"] == "main" and not got["meter_said"]


def test_english_do_is_not_two():
    assert parse_payment("do I add it today", TODAY)["amount"] is None


def test_prefers_the_amount_next_to_rupees():
    assert parse_payment("meter 3000 pe 400 rupees dale", TODAY)["amount"] == 400


def test_flags_what_was_said():
    got = parse_payment("DG 500 on 5 October", TODAY)
    assert got["date_said"] and got["meter_said"]
