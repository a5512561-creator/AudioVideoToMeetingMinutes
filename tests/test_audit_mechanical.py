from script.schemas import SynthesizedMinutes, SynthTopic, SynthAction
from script.audit_mechanical import evaluate, overall_pass


def _good():
    return SynthesizedMinutes(
        topics=[SynthTopic(title="KPI 制度", summary="討論 KPI 是否納入考核。",
                            decisions=["KPI 不納入年度考核"])],
        action_items=[SynthAction(task="試算 KTR 影響", owner="小王",
                                  due="下週五", priority="high")],
    )


def test_empty_minutes_all_pass_vacuously():
    checks = evaluate(SynthesizedMinutes())
    assert all(c.passed for c in checks)
    assert overall_pass(checks) is True


def test_good_minutes_all_pass():
    checks = evaluate(_good())
    keys = {c.key for c in checks}
    assert keys == {
        "action_owner_present", "action_due_present", "decision_nonempty",
        "topic_title_nonempty", "topic_summary_nonempty", "no_placeholder_markers",
    }
    assert all(c.passed for c in checks)
    assert overall_pass(checks) is True


def test_blank_owner_and_due_flag_offending_action_ids():
    s = _good()
    s.action_items[0].owner = "   "
    s.action_items[0].due = ""
    checks = {c.key: c for c in evaluate(s)}
    assert checks["action_owner_present"].passed is False
    assert checks["action_owner_present"].offending == ["A1"]
    assert checks["action_due_present"].passed is False
    assert checks["action_due_present"].offending == ["A1"]
    assert overall_pass(evaluate(s)) is False


def test_blank_decision_flagged_with_dotted_id():
    s = _good()
    s.topics[0].decisions = ["有效決議", "  "]
    checks = {c.key: c for c in evaluate(s)}
    assert checks["decision_nonempty"].passed is False
    assert checks["decision_nonempty"].offending == ["T1.d2"]


def test_blank_title_and_summary_flagged():
    s = _good()
    s.topics[0].title = ""
    s.topics[0].summary = "   "
    checks = {c.key: c for c in evaluate(s)}
    assert checks["topic_title_nonempty"].offending == ["T1"]
    assert checks["topic_summary_nonempty"].offending == ["T1"]


def test_placeholder_markers_detected_across_fields():
    s = _good()
    s.topics[0].summary = "討論 KPI [待確認] 細節"
    s.action_items[0].task = "完成 TODO 的規格"
    checks = {c.key: c for c in evaluate(s)}
    c = checks["no_placeholder_markers"]
    assert c.passed is False
    assert "T1.summary" in c.offending
    assert "A1.task" in c.offending
