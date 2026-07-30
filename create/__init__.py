"""Create-after-audit chapter.

Consumes audit outputs and writes only under projects/<id>/create/.
Never imported by layer0/1/2 — keep the auditor path untouched.
"""

__all__ = ["gaps", "decisions", "brief", "draft", "auth", "tree"]
