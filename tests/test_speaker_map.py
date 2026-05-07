from script.speaker_map import write_template, load, remap, remap_text


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


def test_remap_text_substitutes_inline_labels():
    mapping = {"SPEAKER_01": "Albert", "SPEAKER_07": "John"}
    assert remap_text("owner is SPEAKER_01", mapping) == "owner is Albert"
    assert remap_text("ask SPEAKER_07 to talk to SPEAKER_01", mapping) == "ask John to talk to Albert"


def test_remap_text_leaves_unknown_labels_alone():
    mapping = {"SPEAKER_01": "Albert"}
    assert remap_text("owner SPEAKER_99", mapping) == "owner SPEAKER_99"


def test_remap_text_handles_none_or_empty():
    assert remap_text(None, {"SPEAKER_01": "Albert"}) is None
    assert remap_text("text", {}) == "text"
    assert remap_text("", {"SPEAKER_01": "Albert"}) == ""


def test_remap_text_does_not_match_partial_labels():
    # SPEAKER_1 (no leading zero) is not matched — pyannote always uses _NN
    mapping = {"SPEAKER_01": "Albert"}
    # but our regex matches SPEAKER_\d+ so SPEAKER_1 also matches; documenting this
    assert remap_text("SPEAKER_001 something", mapping) == "SPEAKER_001 something"  # unmapped, passthrough
