import io

from rich.console import Console
from rich.markdown import Markdown

from heavymetal import mascot
from heavymetal.ui import StreamRenderer, banner


def tty(width=140):
    return Console(file=io.StringIO(), width=width, force_terminal=True, color_system=None)


def test_art_round_trips_through_dots():
    assert mascot.encode(mascot.BASE) == [r.ljust(mascot.WIDTH) for r in mascot.ART.rstrip("\n").split("\n")]
    assert (mascot.WIDTH, mascot.HEIGHT) == (50, 18)


def test_every_pose_has_the_same_shape():
    for rows in mascot.POSES.values():
        assert len(rows) == mascot.HEIGHT
        assert all(len(r) == mascot.WIDTH for r in rows)


def test_face_features_found_and_poses_differ():
    assert mascot.LEFT_EYE and mascot.RIGHT_EYE and mascot.SMILE
    assert mascot.POSES[(0, False)] != mascot.POSES[(2, False)]  # mouth opens
    assert mascot.POSES[(0, False)] != mascot.POSES[(0, True)]  # eyes blink
    assert mascot.HAT_CELLS and all(r < mascot.HEIGHT // 2 for _, r in mascot.HAT_CELLS)


def test_animations_cycle():
    assert mascot.talking(0).plain != mascot.talking(2).plain
    assert mascot.talking(0).plain == mascot.talking(12).plain  # mouth x4, sparkles x6 at half speed
    assert mascot.waiting(0.0).plain != mascot.waiting(0.3).plain  # sparkles move
    assert mascot.waiting(0.0).plain != mascot.waiting(1.0).plain  # blink at t=0 vs open eyes
    assert "✦" in mascot.waiting(0.3).plain or "✧" in mascot.waiting(0.3).plain


def test_env_switch_disables(monkeypatch):
    monkeypatch.setenv("HEAVYMETAL_MASCOT", "0")
    assert not mascot.enabled()
    monkeypatch.setenv("HEAVYMETAL_MASCOT", "1")
    assert mascot.enabled()


def test_narrow_or_piped_console_disables():
    assert not mascot.enabled(tty(60))
    assert not mascot.enabled(Console(file=io.StringIO(), width=200))


def test_beside_renders_without_wrapping_the_mascot():
    con = tty()
    con.print(mascot.beside(mascot.talking(2), Markdown("hello **bear**")))
    out = con.file.getvalue()
    assert mascot.POSES[(1, False)][10].rstrip() in out or mascot.POSES[(2, False)][10].rstrip() in out
    assert "hello" in out


def test_banner_renders():
    con = tty()
    con.print(banner())
    assert "agent for Solana" in con.file.getvalue()


def test_waiting_view_runs_until_content_then_bear_rests_beside_text():
    con = tty()
    r = StreamRenderer(con, mascot_enabled=True)
    r.waiting()
    assert r._wait is not None
    r.on_delta("reasoning", "hmm, checking liquidity")
    assert r.reasoning_text == "hmm, checking liquidity"
    r.on_delta("content", "hi ")
    assert r._wait is None and r._live is not None
    r.on_delta("content", "there")
    r.stop()
    out = con.file.getvalue()
    assert "hi there" in out
    assert mascot.POSES[(0, False)][0].rstrip() in out  # idle frame left behind


def test_tools_bring_the_waiting_bear_back():
    con = tty()
    r = StreamRenderer(con, mascot_enabled=True)
    r.waiting()
    r.set_status("token_audit")
    assert r._wait is not None and r.wait_label == "running token_audit"
    r.set_status("")
    assert r._wait is not None and r.wait_label == "thinking"
    r.stop()
    assert r._wait is None
    assert "→ token_audit" in con.file.getvalue()


def test_second_text_segment_is_not_duplicated():
    con = tty()
    r = StreamRenderer(con, mascot_enabled=False)
    r.on_delta("content", "FIRSTSEG")
    r.set_status("swap")
    r.on_delta("content", "SECONDSEG")
    assert r.content_text[r._seg_start :] == "SECONDSEG"  # new live block renders only the new text
    assert r.content_text == "FIRSTSEGSECONDSEG"  # full text kept for the transcript
    r.stop()


def test_without_terminal_no_live_no_mascot():
    con = Console(file=io.StringIO(), width=140)
    r = StreamRenderer(con)
    assert r.mascot is False
    r.waiting()
    assert r._wait is None
    r.on_delta("content", "plain text")
    assert r._live is None
    r.stop()
    assert "plain text" in con.file.getvalue()
