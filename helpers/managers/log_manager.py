"""
A module that provides logging functionality with a table display for events
and their details.

The `LoggerTable` class maintains a circular buffer of events and renders them
in a table format with scrolling rows. It allows you to log events with
timestamps and view them in a styled table. The table supports customization of
the number of rows to display and the style of the borders and headers.

This module can be integrated into a live display using the `rich.live.Live`
and `rich.console.Group` to combine the logger table with other content,
like progress indicators.
"""

from collections import deque
from datetime import datetime

from rich.box import SIMPLE
from rich.panel import Panel
from rich.table import Table

class LoggerTable:
    """
    A class for logging events and displaying them in a table format with
    scrolling rows.

    Args:
        max_rows (int): The maximum number of rows to display in the table.
                        Older entries are removed when the buffer exceeds
                        this size. Default is 4.
        title_color (str): The color used for the table title.
                           Default is "light_cyan3".
        border_style (str): The style of the table's border and column headers.
                            Default is "cyan".
    """

    def __init__(
        self, max_rows=4, title_color="light_cyan3", border_style="cyan"
    ):
        # Circular buffer for scrolling rows
        self.row_buffer = deque(maxlen=max_rows)

        # Create the table with initial setup
        self.title_color = title_color
        self.border_style = border_style
        self.table = self._create_table()

    def log(self, event, details):
        """Add a new row to the table and manage scrolling."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.row_buffer.append((timestamp, event, details))

    def render_log_panel(self):
        """Renders the log panel containing the log table."""
        log_table = self._render_table()
        return Panel(
            log_table,
            title=f"[bold {self.title_color}]Log Messages",
            border_style=self.border_style
        )

    # Private methods
    def _create_table(self):
        """
        Create and return a new table with the necessary columns and styles.
        """
        new_table = Table(
            box=SIMPLE,                    # Box style for the table
            show_header=True,              # Show the table column names
            show_edge=True,                # Display edges around the table
            show_lines=False,              # Do not display grid lines
            border_style=self.title_color  # Set the color of the box
        )
        new_table.add_column(
            f"[{self.title_color}]Timestamp", style="pale_turquoise4", width=15
        )
        new_table.add_column(
            f"[{self.title_color}]Event", style="pale_turquoise1", width=20
        )
        new_table.add_column(
            f"[{self.title_color}]Details", style="pale_turquoise4", width=45
        )
        return new_table

    def _render_table(self):
        """Render the logger table with the current buffer contents."""
        # Create a new table
        new_table = self._create_table()

        # Populate the new table with the row buffer contents
        for row in self.row_buffer:
            new_table.add_row(*row)

        return new_table
