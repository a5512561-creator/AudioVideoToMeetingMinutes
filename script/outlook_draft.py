"""Open a meeting-minutes email as an editable Outlook draft (never sent).

Isolated wrapper around Outlook COM (pywin32). Any failure — pywin32 not
installed, Outlook not available, COM error — is swallowed and reported as
False so the caller can fall back to the written HTML file.
"""


def open_draft(subject: str, html_body: str) -> bool:
    """Create a new Outlook mail item, set subject + HTML body, and open it
    for editing via Display(). Recipients are intentionally left empty.

    Returns True on success, False on any failure.
    """
    try:
        import win32com.client as win32  # type: ignore
        if win32 is None:                # tests may stub this to None
            return False
        app = win32.Dispatch("Outlook.Application")
        mail = app.CreateItem(0)         # 0 = olMailItem
        mail.Subject = subject
        mail.HTMLBody = html_body
        mail.Display(False)              # open editable window; do NOT Send()
        return True
    except Exception:
        return False
