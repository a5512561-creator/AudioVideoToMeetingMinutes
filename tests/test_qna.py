from script.schemas import (
    FinalizedMinutes, FinalTopic, FinalAction, MeetingMeta,
)
from script.qna import run_qna


def _initial():
    return FinalizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        subject="逐字稿檔名",
        topics=[FinalTopic(item="主題A", summary="摘要A"),
                FinalTopic(item="主題B", summary="摘要B")],
        actions=[FinalAction(task="做X", owner="LLM猜的", due="未知", note="")],
    )


def _feeder(lines):
    it = iter(lines)
    return lambda prompt="": next(it)


def test_meta_questions_fill_and_keep_default():
    inp = _feeder([
        "",                      # subject: keep "逐字稿檔名"
        "",                      # meeting_date: keep
        "16:00 - 18:00",         # meeting_time
        "R531",                  # location
        "Max、Heping",           # attendees
        "林冠名",                # recorder
        "spec.docx",             # doc_links
        "rec.mp4",               # video_links
        "",                      # jira: blank (not inferred)
        "",                      # topic A keep
        "",                      # topic B keep
        "n",                     # add topic? no
        "", "Alice", "6/E", "",  # action: keep task, owner, due, note
        "n",                     # add action? no
    ])
    out = lambda *a, **k: None
    f = run_qna(_initial(), inp=inp, out=out)
    assert f.subject == "逐字稿檔名"
    assert f.meta.meeting_time == "16:00 - 18:00"
    assert f.meta.location == "R531"
    assert f.meta.recorder == "林冠名"
    assert f.meta.jira == ""
    assert len(f.topics) == 2
    assert f.actions[0].owner == "Alice" and f.actions[0].due == "6/E"


def test_topic_edit_and_delete_and_add():
    inp = _feeder([
        "x",                          # subject -> "x"
        "", "", "", "", "", "", "",   # 7 meta after date: keep (date,time,loc,att,rec,doc,vid)
        "",                            # jira keep  (8 meta total)
        "e", "主題A改", "摘要A改",     # topic A: edit
        "d",                           # topic B: delete
        "y", "新主題", "新摘要", "n",  # add one topic then stop
        "d",                           # action: delete the only one
        "y", "新任務", "Bob", "今天", "備註X", "n",  # add one action
    ])
    out = lambda *a, **k: None
    f = run_qna(_initial(), inp=inp, out=out)
    assert [t.item for t in f.topics] == ["主題A改", "新主題"]
    assert f.topics[0].summary == "摘要A改"
    assert len(f.actions) == 1
    assert f.actions[0].task == "新任務" and f.actions[0].owner == "Bob"
    assert f.actions[0].due == "今天" and f.actions[0].note == "備註X"


def test_action_keep_still_confirms_owner_due():
    inp = _feeder([
        "",                                  # subject keep
        "", "", "", "", "", "", "", "",      # 8 meta keep
        "", "",                              # topic A keep, topic B keep
        "n",                                 # add topic? no
        "",                                  # action: keep task
        "確認負責人", "6/30", "",            # still asked owner/due/note
        "n",                                 # add action? no
    ])
    out = lambda *a, **k: None
    f = run_qna(_initial(), inp=inp, out=out)
    assert f.actions[0].task == "做X"
    assert f.actions[0].owner == "確認負責人"
    assert f.actions[0].due == "6/30"
