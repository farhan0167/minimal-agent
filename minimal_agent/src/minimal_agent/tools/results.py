"""Result types for the validation and permission pipeline stages.

Kept as tiny closed unions so future variants (e.g. `PermissionAllowOnce`)
can be added without breaking the `Ok | Err` / `Allow | Deny` shape.
"""

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class ValidationOk:
    ok: Literal[True] = True


@dataclass
class ValidationErr:
    message: str
    ok: Literal[False] = False


ValidationResult = Union[ValidationOk, ValidationErr]


@dataclass
class PermissionAllow:
    decision: Literal["allow"] = "allow"


@dataclass
class PermissionDeny:
    reason: str
    decision: Literal["deny"] = "deny"


PermissionResult = Union[PermissionAllow, PermissionDeny]
