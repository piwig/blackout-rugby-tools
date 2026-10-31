"""Independent integer invariants for the indicative stadium allocation."""
from decimal import Decimal, ROUND_HALF_UP

import pytest

from server.domain import stadium_plan


@pytest.mark.parametrize('members,multiplier,expected', [
    (1, 9, 9), (7, 9, 63), (73, 9, 657), (1001, 9, 9009),
    (1000, 10, 10000), (0, 9, 0), (1001, 9.5, 9510), (25, 5.1, 128), (30, 8.45, 254),
])
def test_stadium_allocation_conserves_rounded_total(members, multiplier, expected):
    result = stadium_plan(members, {}, multiplier)
    assert result['target_total'] == expected
    assert sum(section['target'] for section in result['sections']) == expected
    assert result['to_add'] == expected


def test_stadium_small_total_gives_last_seat_to_largest_remainder():
    # Nine seats: exact shares 1.98, 3.51, 2.70, .72, .09. Floors total 6;
    # the three remaining seats go to standing, members, covered, in that order.
    result = stadium_plan(1, {}, 9)
    assert [section['target'] for section in result['sections']] == [2, 3, 3, 1, 0]


def test_stadium_allocation_is_bounded_and_current_seats_do_not_change_targets():
    ratios = (22, 39, 30, 8, 1)
    for members in (*range(101), 999, 1001, 999999, 1000000):
        for multiplier in (1, 9, 9.5, 20):
            total = int((Decimal(str(members))*Decimal(str(multiplier))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            result = stadium_plan(members, {'standing': 99999999}, multiplier)
            assert result['target_total'] == total
            assert result['sections'][0]['to_add'] == 0
            for section, ratio in zip(result['sections'], ratios):
                floor, remainder = divmod(total*ratio, 100)
                assert section['target'] in (floor, floor+int(remainder > 0))
                assert section['to_add'] >= 0
            assert result['to_add'] == sum(section['to_add'] for section in result['sections'])
