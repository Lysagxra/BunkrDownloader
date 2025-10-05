"""Module that provides a logging table display for events and their details.

The `LoggerTable` class maintains a circular buffer of events and renders them in a
table format with scrolling rows. It allows you to log events with timestamps and view
them in a styled table. The table supports customization of the number of rows to
display and the style of the borders and headers.

This module can be integrated into a live display using the `rich.live.Live` and
`rich.console.Group` to combine the logger table with other content, like progress
indicators.
"""

import logging
import shutil
from collections import deque
from datetime import datetime, timezone

from rich.box import SIMPLE
from rich.panel import Panel
from rich.table import Table

from src.config import LOG_MANAGER_CONFIG

logging.basicConfig(level=logging.INFO, format="%(message)s")


class LoggerTable:
    """Class for logging events and displaying them in a table with scrolling rows."""

    def __init__(
        self,
        max_rows: int = 4,
    ) -> None:
        """Initialize the table with a circular buffer for scrolling rows."""
        # Circular buffer for scrolling rows
        self.row_buffer = deque(maxlen=max_rows)

        # Create the table with initial setup
        self.title_color = LOG_MANAGER_CONFIG["colors"]["title_color"]
        self.border_style = LOG_MANAGER_CONFIG["colors"]["border_color"]
        self.table = self._create_table()

    def log(self, event: str, details: str, *, disable_ui: bool = False) -> None:
        """Add a new row to the table and manage scrolling."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

        if not disable_ui:
            self.row_buffer.append((timestamp, event, details))

        else:
            log_message = f"[{timestamp}] Event: {event} | Details: {details}"
            logging.info(log_message)

    def render_log_panel(self, panel_width: int = 40) -> Panel:
        """Render the log panel containing the log table."""
        log_table = self._render_table()
        return Panel.fit(
            log_table,
            title=f"[bold {self.title_color}]Log Messages",
            border_style=self.border_style,
            width=2*panel_width,  # Log panel width is double the single table width
        )

    # Private methods
    def _calculate_column_widths(
        self, min_column_widths: dict, padding: int = 10,
    ) -> dict:
        """Calculate the column widths based on the terminal width."""
        terminal_width, _ = shutil.get_terminal_size()
        available_width = terminal_width - padding
        total_min_width = sum(min_column_widths.values())

        # If the available width is less than the minimum width, use the minimum width
        if available_width < total_min_width:
            return min_column_widths

        # Calculate the remaining space after allocating the minimum widths
        remaining_width = available_width - total_min_width

        # Distribute the remaining width equally across the columns
        return {
            column: min_width + remaining_width // len(min_column_widths)
            for column, min_width in min_column_widths.items()
        }

    def _create_table(self) -> Table:
        """Create and return a new table with the necessary columns and styles."""
        # Calculate the dynamic column widths
        min_column_widths = LOG_MANAGER_CONFIG["min_column_widths"]
        column_widths = self._calculate_column_widths(min_column_widths)

        # List of columns to add to the table
        column_styles = LOG_MANAGER_CONFIG["column_styles"]
        column_names = ["Timestamp", "Event", "Details"]

        new_table = Table(
            box=SIMPLE,                     # Box style for the table
            show_header=True,               # Show the table column names
            show_edge=True,                 # Display edges around the table
            show_lines=False,               # Do not display grid lines
            border_style=self.title_color,  # Set the color of the box
        )

        # Add columns dynamically
        for name in column_names:
            new_table.add_column(
                f"[{self.title_color}]{name}",
                style=column_styles[name],
                width=column_widths[name],
            )

        return new_table

    def _render_table(self) -> Table:
        """Render the logger table with the current buffer contents."""
        # Create a new table
        new_table = self._create_table()

        # Populate the new table with the row buffer contents
        for row in self.row_buffer:
            new_table.add_row(*row)

        return new_table
