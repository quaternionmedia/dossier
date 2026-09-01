"""Pick a harness tool to run, from the Seams screen.

**RUNNING A TOOL IS A WRITE TO THE HARNESS**, the one act dossier's harness
client starts rather than reads. This screen only chooses which; the app runs it
in a worker and reports the invocation the harness began, because a run can take
longer than a keystroke and the loop a person is looking at must not stop for it.

The screen dismisses with a tool name, or `None` when it is escaped or there is
nothing to run -- an unreachable harness or a harness offering no tools both
say so here rather than looking like an empty picker that failed to load.
"""

from __future__ import annotations

from typing import Any

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


class ToolPickerScreen(ModalScreen):
    """A modal list of the harness's tools; selecting one returns its name."""

    CSS = """
    ToolPickerScreen { align: center middle; }
    #tool-picker {
        width: 72; height: auto; max-height: 80%;
        border: round $primary; background: $surface; padding: 1 2;
    }
    #tool-picker-title { text-style: bold; padding-bottom: 1; }
    #tool-picker-note { color: $text-muted; }
    #tool-list { height: auto; max-height: 20; }
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, listing: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._listing = listing  # dossier.human.ToolListing

    def compose(self):
        with Vertical(id="tool-picker"):
            yield Static("Run a harness tool", id="tool-picker-title")
            if not self._listing.reachable:
                yield Static(
                    f"{self._listing.problem}\n{self._listing.remedy}",
                    id="tool-picker-note")
            elif not self._listing.tools:
                yield Static("The harness is reachable but offers no tools.",
                             id="tool-picker-note")
            else:
                yield OptionList(
                    *[Option(self._label(tool), id=tool.name)
                      for tool in self._listing.tools],
                    id="tool-list")

    @staticmethod
    def _label(tool: Any) -> str:
        desc = f" -- {tool.description}" if tool.description else ""
        line = f"{tool.name}{desc}"
        return line if len(line) <= 66 else line[:65] + "…"

    def on_option_list_option_selected(
            self, event: OptionList.OptionSelected) -> None:
        # The option id is the tool name; the app runs it in a worker.
        self.dismiss(event.option.id)

    def action_dismiss(self, result: Any = None) -> None:
        self.dismiss(None)
