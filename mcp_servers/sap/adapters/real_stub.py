"""Placeholder for the real SAP route. Nothing here is implemented or verified.

TODO(verify): the route (report export, released API or CDS views, or other), SAP version
(ECC or S/4), RISE edition, and a read-only service login are all unknown until discovery with
Dan. Do not name SAP tables, T-codes or BAPIs here until he confirms them.
"""

from __future__ import annotations

from mcp_servers.sap.interface import ReadQuery, ReadResult


class RealSapReader:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def read(self, query: ReadQuery) -> ReadResult:
        raise NotImplementedError(
            "TODO(verify): the real SAP route is not decided. Use the mock adapter for now."
        )
