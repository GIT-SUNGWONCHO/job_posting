import json

from jobpost import notes


class FakeStore:
    def __init__(self, users):
        self.users = users
        self.inserted = []

    def select(self, table, query="select=*"):
        assert table == "profiles"
        return [{"user_id": u} for u in self.users]

    def insert(self, table, rows):
        assert table == "research_notes"
        self.inserted.extend(rows)


def note(**kw):
    base = {"v": 1, "company": "삼성생명", "name": "삼성생명", "updated": "2026-10-23", "summary": ["요약"],
            "sections": [{"title": "회사·사업", "blocks": [{"t": "facts", "items": ["사실"]}],
                          "sources": [{"title": "IR", "url": "https://example.com"}]}]}
    return {**base, **kw}


def write(tmp_path, name, data):
    d = tmp_path / "notes"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_saves_note_for_only_user(tmp_path):
    write(tmp_path, "a.json", note())
    store = FakeStore(["u1"])
    summary = notes.run(tmp_path, store)
    assert summary == {"files": 1, "saved": 1, "skipped": []}
    assert store.inserted[0]["user_id"] == "u1" and store.inserted[0]["company_key"] == "삼성생명"
    assert store.inserted[0]["updated_on"] == "2026-10-23"


def test_skips_bad_notes(tmp_path):
    bad = note()
    bad["sections"][0]["sources"] = []
    bad["sections"][0]["blocks"].append({"t": "chart"})
    write(tmp_path, "bad.json", bad)
    write(tmp_path, "b.json", note(company="카카오", name="카카오"))
    store = FakeStore(["u1", "u2"])  # 두 사람이면 user_id가 있어야 한다
    summary = notes.run(tmp_path, store)
    assert summary["saved"] == 0 and summary["skipped"] == ["b.json", "bad.json"]
    errs = notes.problems(bad)
    assert any("출처 없음" in e for e in errs) and any("모르는 블록 chart" in e for e in errs)


def test_user_id_in_file_wins_and_is_not_stored(tmp_path):
    write(tmp_path, "a.json", note(user_id="u2"))
    store = FakeStore(["u1", "u2"])
    notes.run(tmp_path, store)
    assert store.inserted[0]["user_id"] == "u2" and "user_id" not in store.inserted[0]["note"]
