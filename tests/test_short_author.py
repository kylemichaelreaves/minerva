"""``short_author`` labels the citation-matrix axes; distinct authors
must not collapse onto the same truncated label."""

from minerva.refs.row_utils import short_author


def test_luther_editions_stay_distinct():
    assert short_author("Luther Bibel 1545") == "Luther 1545"
    assert short_author("Luther Bibel 1912") == "Luther 1912"


def test_long_unlisted_name_is_truncated():
    assert short_author("Boulainvilliers") == "Boulainvill…"


def test_short_name_is_unchanged():
    assert short_author("Plato") == "Plato"
