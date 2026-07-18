from script.text_format import to_sentences


def test_splits_on_cjk_terminators_keeping_them():
    s = to_sentences("霸凌需刻意針對特定人。身心危害不需證明實際損害。需綜合評估。")
    assert s == [
        "霸凌需刻意針對特定人。",
        "身心危害不需證明實際損害。",
        "需綜合評估。",
    ]


def test_no_terminator_returns_single_item():
    assert to_sentences("一句沒有句號的摘要") == ["一句沒有句號的摘要"]


def test_empty_and_whitespace_yield_empty_list():
    assert to_sentences("") == []
    assert to_sentences("   \n  ") == []


def test_splits_on_newlines_too():
    assert to_sentences("第一點\n第二點") == ["第一點", "第二點"]


def test_ascii_period_does_not_split_but_bang_question_do():
    # ASCII '.' is intentionally NOT a terminator (would wreck decimals /
    # "e.g." / "1.5"); ASCII ! and ? still split.
    s = to_sentences("See figure 1.5 now. 中文說明？好的！")
    assert s == ["See figure 1.5 now. 中文說明？", "好的！"]


def test_drops_blank_fragments_between_terminators():
    # trailing terminator must not produce an empty final item
    assert to_sentences("甲。乙。") == ["甲。", "乙。"]
