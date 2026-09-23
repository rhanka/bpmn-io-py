# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/Grid.js (MIT).
"""The layout grid transposed from ``lib/Grid.js``.

Identity rules: ``find`` compares with ``is`` and ``get_elements_total`` dedups
by ``id()`` (a literal ``Set`` would rely on value equality upstream never uses).
``get`` on a missing cell returns ``None`` (``undefined``); negative indices are
missing too, mirroring ``(grid[row] || [])[col]``. The ``expand_row`` upper-bound
clause compares against ``NaN`` exactly as upstream (``this.rowCount`` is
``undefined`` there), so it stays dead; it is deliberately not "fixed".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from bpmn_io._js import is_truthy
from bpmn_io.auto_layout.errors import LayoutError

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Grid"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any

#: Stand-in for upstream ``this.rowCount`` (``undefined``, so ``- 1`` is ``NaN``).
_MISSING_ROW_COUNT = float("nan")


def _is_integer(value: Element) -> bool:
    """Return ``Number.isInteger(value)`` (bools are not integers, as upstream)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


class Grid:
    """A sparse row/column placement of flow elements."""

    def __init__(self) -> None:
        """Create an empty grid."""
        self.grid: list[list[Element]] = []

    def add(self, element: Element, position: Sequence[int] | None = None) -> None:
        """Place ``element`` at ``position`` (E1 when the cell is occupied)."""
        if position is None or not is_truthy(position):
            self._add_start(element)
            return

        row, col = position
        if not is_truthy(row) and not is_truthy(col):
            self._add_start(element)

        while len(self.grid) <= row:
            self.grid.append([])

        if is_truthy(self.get(row, col)):
            msg = "Grid is occupied please ensure the place you insert at is not occupied"
            raise LayoutError(msg)

        target = self.grid[row]
        while len(target) <= col:
            target.append(None)
        target[col] = element

    def create_row(self, after_index: int | None = None) -> None:
        """Append a row, or splice one in after ``after_index``."""
        if after_index is None or (not is_truthy(after_index) and not _is_integer(after_index)):
            self.grid.append([])
        else:
            self.grid.insert(after_index + 1, [])

    def _add_start(self, element: Element) -> None:
        """Push a first row holding ``element``."""
        self.grid.append([element])

    def add_after(self, element: Element, new_element: Element) -> None:
        """Splice ``new_element`` right after ``element`` in its row."""
        if not is_truthy(element):
            self._add_start(new_element)
        row, col = self.find(element)
        self.grid[row].insert(col + 1, new_element)

    def add_below(self, element: Element, new_element: Element) -> None:
        """Place ``new_element`` below ``element`` (E2 when no place is found)."""
        if not is_truthy(element):
            self._add_start(new_element)

        row, col = self.find(element)

        # We are at the bottom of the current grid - add empty row below
        if row + 1 >= len(self.grid):
            self.grid.append([])

        # The element below is already occupied - insert new row
        if is_truthy(self.get(row + 1, col)):
            self.grid.insert(row + 1, [])

        if is_truthy(self.get(row + 1, col)):
            msg = "Grid is occupied and we could not find a place - this should not happen"
            raise LayoutError(msg)

        target = self.grid[row + 1]
        while len(target) <= col:
            target.append(None)
        target[col] = new_element

    def find(self, element: Element) -> tuple[int, int]:
        """Return the ``(row, col)`` of ``element`` (``(-1, -1)`` when absent)."""
        for row_index, row in enumerate(self.grid):
            for col_index, candidate in enumerate(row):
                if candidate is element:
                    return (row_index, col_index)
        return (-1, -1)

    def get(self, row: int, col: int) -> Element:
        """Return the cell at ``(row, col)`` (``None`` when missing)."""
        if row < 0 or col < 0:
            return None
        if row >= len(self.grid):
            return None
        row_list = self.grid[row]
        if col >= len(row_list):
            return None
        return row_list[col]

    def get_elements_in_range(self, start: dict[str, int], end: dict[str, int]) -> list[Element]:
        """Return the occupied cells of the inclusive ``start``/``end`` rectangle."""
        start_row = start["row"]
        start_col = start["col"]
        end_row = end["row"]
        end_col = end["col"]

        if start_row > end_row:
            start_row, end_row = end_row, start_row

        if start_col > end_col:
            start_col, end_col = end_col, start_col

        elements = []
        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                element = self.get(row, col)

                if is_truthy(element):
                    elements.append(element)
        return elements

    def adjust_grid_position(self, element: Element) -> None:
        """Move ``element`` to the next free column end (task-fan-out spacing)."""
        row, col = self.find(element)
        _num_rows, max_col = self.get_grid_dimensions()

        if col < max_col - 1:
            # add element in next column
            row_list = self.grid[row]
            del row_list[max_col:]
            while len(row_list) < max_col:
                row_list.append(None)
            row_list.append(element)
            row_list[col] = None

    def adjust_row_for_multiple_incoming(
        self, elements: list[Element], current_element: Element
    ) -> None:
        """Pull ``current_element`` up to the lowest incoming row when free."""
        results = [self.find(element) for element in elements]

        # filter only rows that currently exist, excluding any future or non-existent rows
        lowest_row = min(
            [result_row for result_row, _ in results if result_row >= 0],
            default=float("inf"),
        )

        row, col = self.find(current_element)

        # if element doesn't already exist in current row, add element
        if lowest_row < row and not is_truthy(self.get(int(lowest_row), col)):
            target = self.grid[int(lowest_row)]
            while len(target) <= col:
                target.append(None)
            target[col] = current_element
            self.grid[row][col] = None

    def adjust_column_for_multiple_incoming(
        self, elements: list[Element], current_element: Element
    ) -> None:
        """Push ``current_element`` past the rightmost incoming column."""
        results = [self.find(element) for element in elements]

        # filter only col that currently exist, excluding any future or non-existent col
        max_col = max(
            [result_col for _, result_col in results if result_col >= 0],
            default=float("-inf"),
        )

        row, col = self.find(current_element)

        # add to the next column
        if max_col + 1 > col:
            next_col = int(max_col) + 1
            row_list = self.grid[row]
            while len(row_list) <= next_col:
                row_list.append(None)
            row_list[next_col] = current_element
            row_list[col] = None

    def get_all_elements(self) -> list[Element]:
        """Return every occupied cell, row by row."""
        elements = []

        for row in range(len(self.grid)):
            for col in range(len(self.grid[row])):
                element = self.get(row, col)

                if is_truthy(element):
                    elements.append(element)
        return elements

    def get_grid_dimensions(self) -> tuple[int, int]:
        """Return ``(num_rows, max_cols)`` of the grid."""
        num_rows = len(self.grid)
        max_cols = 0

        for index in range(num_rows):
            current_row_length = len(self.grid[index])
            max_cols = max(max_cols, current_row_length)

        return (num_rows, max_cols)

    def elements_by_position(self) -> list[tuple[Element, int, int]]:
        """Return ``(element, row, col)`` for every occupied cell, row by row."""
        elements = []

        for row_index, row in enumerate(self.grid):
            for col_index, element in enumerate(row):
                if not is_truthy(element):
                    continue
                elements.append((element, row_index, col_index))
        return elements

    def get_elements_total(self) -> int:
        """Return the count of distinct elements (identity dedup)."""
        seen: set[int] = set()
        for row in self.grid:
            for value in row:
                if is_truthy(value):
                    seen.add(id(value))
        return len(seen)

    def create_col(self, after_index: int | None = None, col_count: int | None = None) -> None:
        """Expand every row with ``col_count`` cells (one when absent)."""
        for row_index in range(len(self.grid)):
            self.expand_row(row_index, after_index, col_count)

    def expand_row(
        self,
        row_index: int,
        after_index: int | None = None,
        col_count: int | None = None,
    ) -> None:
        """Splice placeholder cells into one row (dead upper-bound clause kept)."""
        # `this.rowCount` is `undefined` upstream, so `rowIndex > undefined - 1`
        # is `rowIndex > NaN`, always false; the clause stays dead here too.
        if not _is_integer(row_index) or row_index < 0 or row_index > _MISSING_ROW_COUNT - 1:
            return

        count = col_count if isinstance(col_count, int) and col_count > 0 else 1
        placeholder: list[Element] = [None] * count

        row = self.grid[row_index]

        if after_index is None or (not is_truthy(after_index) and not _is_integer(after_index)):
            row[len(row) : len(row)] = placeholder
        else:
            index = after_index + 1
            row[index:index] = placeholder
