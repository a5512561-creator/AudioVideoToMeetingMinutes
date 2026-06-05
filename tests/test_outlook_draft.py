import sys
import types
import pytest
from unittest.mock import MagicMock
from script.outlook_draft import open_draft


@pytest.fixture(autouse=True)
def _restore_win32com():
    saved = {k: sys.modules.get(k) for k in ("win32com", "win32com.client")}
    yield
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def _install_fake_win32com(dispatch_return):
    """Install a fake win32com.client module; return the created MailItem mock."""
    mod = types.ModuleType("win32com")
    client = types.ModuleType("win32com.client")
    client.Dispatch = MagicMock(return_value=dispatch_return)
    mod.client = client
    sys.modules["win32com"] = mod
    sys.modules["win32com.client"] = client
    return client


def test_open_draft_sets_body_and_displays_without_sending(monkeypatch):
    mail = MagicMock()
    app = MagicMock()
    app.CreateItem.return_value = mail
    _install_fake_win32com(app)

    ok = open_draft("主旨X", "<div>內容</div>")

    assert ok is True
    app.CreateItem.assert_called_once_with(0)      # 0 = olMailItem
    assert mail.Subject == "主旨X"
    assert mail.HTMLBody == "<div>內容</div>"
    mail.Display.assert_called_once_with(False)    # opened editable (non-modal), not sent
    mail.Send.assert_not_called()


def test_open_draft_returns_false_on_com_error(monkeypatch):
    client = _install_fake_win32com(MagicMock())
    client.Dispatch.side_effect = RuntimeError("no Outlook")
    assert open_draft("s", "<p>x</p>") is False


def test_open_draft_returns_false_when_pywin32_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "win32com", None)
    monkeypatch.setitem(sys.modules, "win32com.client", None)
    assert open_draft("s", "<p>x</p>") is False
