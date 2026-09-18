"""Membership application pipeline.

An hourly, Polars-based pipeline that ingests batches of membership
applications, cleans and validates them, mints membership IDs for successful
applicants, and writes successful and unsuccessful applications to separate
folders for downstream consumers.

Every transformation in this package is a pure function returning a
``pl.LazyFrame`` or ``pl.Expr``.  The query graph stays lazy end to end;
:mod:`membership_pipeline.output` is the only module that materialises it.
"""

from __future__ import annotations

__version__ = "1.0.0"
