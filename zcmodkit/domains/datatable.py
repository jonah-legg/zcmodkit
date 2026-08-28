"""Editing DataTable rows.

A cooked DataTable is its own properties, then a row count, then every row as a
name followed by a struct. Most of the game's tuning sits in tables like this.
Ability costs, weapon stats, upgrade curves. That makes them the most useful
thing to be able to edit by name.
"""

from __future__ import annotations

import struct

from ..formats.usmap import Mappings, bundled
from ..formats.zen import ZenPackage
from .properties import Located, PropertyError, read_struct, write_number


class DataTableError(ValueError):
    """A package was not a DataTable, or would not parse as one."""


class DataTable:
    """Row by row access to a cooked DataTable."""

    def __init__(
        self,
        package_path: str,
        data: bytearray,
        mappings: Mappings | None = None,
        row_struct: str | None = None,
    ):
        self.package_path = package_path
        self.data = data
        self.mappings = mappings or bundled()
        self.row_struct = row_struct
        self.changes = 0
        self._read()

    def _read(self) -> None:
        pkg = ZenPackage(self.data)
        self.package = pkg
        try:
            _, after = read_struct(
                self.data, pkg.header_size, "DataTable", self.mappings
            )
        except PropertyError as exc:
            raise DataTableError(
                f"{self.package_path} is not a DataTable: {exc}"
            ) from exc

        at = after + 4  # marker between the table properties and the rows
        (count,) = struct.unpack_from("<i", self.data, at)
        self._rows_at = at + 4
        if not 0 <= count < 100_000:
            raise DataTableError(
                f"implausible row count {count} in {self.package_path}"
            )
        self._row_count = count

        if self.row_struct is None:
            self.row_struct = self._resolve_row_struct()
        self.rows = self._walk(self.row_struct)

    def _walk(self, row_struct: str) -> dict[str, dict[str, Located]]:
        """Read every row, and insist the walk finishes exactly at the end.

        Finishing anywhere else means the schema is wrong for this asset.
        Either the row struct is not the right one, or the mappings came from a
        different build. Either way none of the offsets can be trusted.
        """
        pkg, at = self.package, self._rows_at
        rows: dict[str, dict[str, Located]] = {}
        for _ in range(self._row_count):
            (name_index, _number) = struct.unpack_from("<II", self.data, at)
            at += 8
            name = (
                pkg.names[name_index]
                if name_index < len(pkg.names)
                else str(name_index)
            )
            props, at = read_struct(self.data, at, row_struct, self.mappings)
            rows[name] = props
        if at != len(self.data):
            raise DataTableError(
                f"{self.package_path}: rows ended at {at} of {len(self.data)} "
                f"bytes using {row_struct}"
            )
        return rows

    def _resolve_row_struct(self) -> str:
        """Work out the row struct by trying the likely ones.

        A DataTable points at its row struct through the import map, not the
        name map, so there is no name to read off. Guessing is safe here
        because only the correct struct walks the table byte for byte.
        """
        candidates = [n for n in self.mappings.schemas if n.endswith("TableRow")]
        candidates += [
            n
            for n in self.mappings.schemas
            if n.endswith("Row") and not n.endswith("TableRow")
        ]
        for name in candidates:
            try:
                self._walk(name)
            except (DataTableError, PropertyError, struct.error, IndexError):
                continue
            return name
        raise DataTableError(
            f"could not work out the row struct for {self.package_path}. "
            "Pass row_struct= if you know it."
        )

    def row(self, name: str) -> dict[str, Located]:
        """One row's properties, by row name."""
        try:
            return self.rows[name]
        except KeyError:
            raise DataTableError(
                f"{self.package_path} has no row {name!r}. "
                f"It has {len(self.rows)}, for example {list(self.rows)[:3]}"
            ) from None

    def get(self, row: str, field: str):
        """One value from one row."""
        props = self.row(row)
        if field not in props:
            raise DataTableError(
                f"row {row!r} has no field {field!r}; it has {sorted(props)}"
            )
        return props[field].value

    def set(self, row: str, field: str, value: float) -> DataTable:
        """Overwrite a number. Numbers are fixed width, so nothing shifts."""
        props = self.row(row)
        if field not in props:
            raise DataTableError(
                f"row {row!r} has no field {field!r}; it has {sorted(props)}"
            )
        write_number(self.data, props[field], value)
        self.changes += 1
        self._read()  # refresh the cached values
        return self

    def set_all(self, field: str, value: float) -> DataTable:
        """Overwrite a field in every row that has one."""
        for name, props in list(self.rows.items()):
            if field in props and props[field].offset >= 0:
                write_number(self.data, props[field], value)
                self.changes += 1
                del name
        self._read()
        return self

    def __len__(self) -> int:
        return len(self.rows)

    def __repr__(self) -> str:
        return (
            f"<DataTable {self.package_path.rsplit('/', 1)[-1]} "
            f"rows={len(self.rows)} struct={self.row_struct} changes={self.changes}>"
        )
