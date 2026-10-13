"""Read-only SAP access interface. Domain-neutral: entity names are chosen by the caller."""

from mcp_servers.sap.interface import ReadQuery, ReadResult, SapReader

__all__ = ["ReadQuery", "ReadResult", "SapReader"]
