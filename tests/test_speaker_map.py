from script.speaker_map import write_template, load, remap


def test_write_template_creates_identity_mapping(tmp_path):
    dst = tmp_path / "speaker_map.json"
    write_template(str(dst), ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"])
    data = load(str(dst))
    assert data == {"SPEAKER_00": "SPEAKER_00", "SPEAKER_01": "SPEAKER_01"}


def test_write_template_does_not_overwrite_existing(tmp_path):
    dst = tmp_path / "speaker_map.json"
    dst.write_text('{"SPEAKER_00": "Albert"}', encoding="utf-8")
    write_template(str(dst), ["SPEAKER_00", "SPEAKER_01"])
    # User-edited file preserved
    assert load(str(dst)) == {"SPEAKER_00": "Albert"}


def test_load_returns_empty_dict_when_missing(tmp_path):
    assert load(str(tmp_path / "nope.json")) == {}


def test_remap_substitutes_when_present():
    assert remap("SPEAKER_00", {"SPEAKER_00": "Albert"}) == "Albert"


def test_remap_passes_through_when_absent():
    assert remap("SPEAKER_99", {"SPEAKER_00": "Albert"}) == "SPEAKER_99"


def test_remap_handles_none():
    assert remap(None, {}) is None
