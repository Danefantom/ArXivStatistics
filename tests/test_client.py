from datetime import date

import pytest

from quantum_trends.arxiv_client import ArxivClient, RetrievalError, base_id, default_dates, parse_feed


def test_atom_error_feed_is_not_silently_empty():
    xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#bad_query</id><title>Error</title><summary>Invalid query</summary></entry></feed>'''
    with pytest.raises(RetrievalError, match="Invalid query"):
        parse_feed(xml)


def test_atom_namespaces_original_date_and_base_id():
    xml = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/" xmlns:x="http://arxiv.org/schemas/atom"><o:totalResults>1</o:totalResults><o:startIndex>0</o:startIndex><entry><id>http://arxiv.org/abs/2601.12345v3</id><title>Quantum\n dynamics</title><summary>GKSL evolution</summary><published>2026-01-01T23:59:59Z</published><updated>2026-03-02T00:00:00Z</updated><category term="quant-ph"/><x:primary_category term="quant-ph"/><author><name>A. Author</name></author></entry></feed>'''
    total, offset, rows = parse_feed(xml)
    assert (total, offset) == (1, 0)
    assert rows[0]["id"] == "2601.12345"
    assert rows[0]["published"] == "2026-01-01T23:59:59Z"
    assert rows[0]["title"] == "Quantum dynamics"
    assert rows[0]["authors"] == ["A. Author"]
    assert base_id("http://arxiv.org/abs/quant-ph/9901234v2") == "quant-ph/9901234"


def record(i, timestamp):
    return {"id": str(i), "published": timestamp, "categories": ["quant-ph"]}


def test_last_second_is_retained_next_midnight_trimmed(tmp_path):
    client = ArxivClient(tmp_path)
    def page(query, offset):
        assert "202602010000" in query
        return 2, 0, [record(1, "2026-01-31T23:59:59Z"), record(2, "2026-02-01T00:00:00Z")]
    client.page = page
    rows, total, excluded = client.interval(date(2026,1,1), date(2026,1,31))
    assert [r["id"] for r in rows] == ["1"]
    assert total == 2
    assert excluded == 1


def test_short_and_duplicated_pagination_fail(tmp_path):
    client = ArxivClient(tmp_path)
    client.page = lambda q, start: (2, start, [record(1, "2026-01-01T12:00:00Z")] if start == 0 else [])
    with pytest.raises(RetrievalError, match="pagination"):
        client.interval(date(2026,1,1), date(2026,1,1))
    client.page = lambda q, start: (2, start, [record(1, "2026-01-01T12:00:00Z")])
    with pytest.raises(RetrievalError, match="Duplicate"):
        client.interval(date(2026,1,1), date(2026,1,1))


def test_subdivision_accounting_includes_shared_midnight_once(tmp_path):
    client = ArxivClient(tmp_path)
    first = [record(i, "2026-01-01T23:59:59Z") for i in range(600)]
    midnight = record(600, "2026-01-02T00:00:00Z")
    last = [record(i, "2026-01-02T12:00:00Z") for i in range(601,1001)]
    def page(query, offset):
        if "202601010000 TO 202601030000" in query:
            return 1001, 0, first[:500]
        rows = first + [midnight] if "202601010000 TO 202601020000" in query else [midnight] + last
        return len(rows), offset, rows[offset:offset+500]
    client.page = page
    rows, total, excluded = client.interval(date(2026,1,1), date(2026,1,2))
    assert len(rows) == len({p["id"] for p in rows}) == total == 1001
    assert excluded == 0


def test_default_dates_cross_year_and_invalid_interval(tmp_path):
    assert default_dates(12, date(2026,11,23)) == (date(2025,12,1), date(2026,11,23))
    with pytest.raises(ValueError):
        default_dates(0)
    with pytest.raises(ValueError, match="start"):
        ArxivClient(tmp_path).fetch(date(2026,1,2), date(2026,1,1))
