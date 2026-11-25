"""The operating contract, read back from the resource tags written by infra/types/contract.bicep.

The contract is the envelope. Nothing in this server may set a container app's scale range outside it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

TAG_MANAGED = "aiops-managed"
TAG_OWNER = "aiops-owner"
TAG_MIN = "aiops-min-replicas"
TAG_MAX = "aiops-max-replicas"
TAG_MODE = "aiops-change-mode"
TAG_TIER = "aiops-tier"
TAG_SLO = "aiops-slo-p95-ms"
TAG_BUDGET = "aiops-budget-eur"

REQUIRED_TAGS = (TAG_MANAGED, TAG_OWNER, TAG_MIN, TAG_MAX, TAG_MODE, TAG_TIER)


class ContractError(ValueError):
    """The resource has no usable operating contract."""


@dataclass(frozen=True)
class Contract:
    owner: str
    min_replicas: int
    max_replicas: int
    change_mode: str  # review | autonomous
    tier: str  # prod | nonprod
    slo_p95_ms: int = 0
    budget_eur: int = 0

    @property
    def effective_mode(self) -> str:
        """Production is always review, whatever the tag says. Same rule as the contract type in Bicep."""
        return "review" if self.tier == "prod" else self.change_mode

    def to_dict(self) -> dict:
        d = asdict(self)
        d["effective_mode"] = self.effective_mode
        return d

    @classmethod
    def from_tags(cls, tags: dict[str, str] | None) -> "Contract":
        tags = {k.lower(): v for k, v in (tags or {}).items()}
        missing = [t for t in REQUIRED_TAGS if t not in tags]
        if missing:
            raise ContractError(f"missing contract tags: {', '.join(missing)}")
        if tags[TAG_MANAGED].lower() != "true":
            raise ContractError(f"{TAG_MANAGED} is not 'true'; the agent does not manage this resource")
        try:
            lo, hi = int(tags[TAG_MIN]), int(tags[TAG_MAX])
            slo, budget = int(tags.get(TAG_SLO, "0") or 0), int(tags.get(TAG_BUDGET, "0") or 0)
        except ValueError as ex:
            raise ContractError(f"contract tag is not an integer: {ex}") from ex
        mode, tier = tags[TAG_MODE].lower(), tags[TAG_TIER].lower()
        if mode not in ("review", "autonomous"):
            raise ContractError(f"{TAG_MODE} must be review or autonomous, got {mode!r}")
        if tier not in ("prod", "nonprod"):
            raise ContractError(f"{TAG_TIER} must be prod or nonprod, got {tier!r}")
        if not (0 <= lo <= hi and hi >= 1 and hi <= 1000):
            raise ContractError(f"invalid replica envelope {lo}..{hi}")
        return cls(tags[TAG_OWNER], lo, hi, mode, tier, slo, budget)


@dataclass
class ScaleDecision:
    allowed: bool
    apply: bool
    mode: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_scale_request(
    contract: Contract,
    current_min: int,
    current_max: int,
    new_min: int,
    new_max: int,
    reason: str,
    *,
    writes_enabled: bool,
    dry_run: bool,
    max_step: int,
) -> ScaleDecision:
    """Decide whether a scale-range change is inside the contract, and whether it may be applied now.

    allowed = the change is inside the envelope. apply = the server will actually call Azure.
    """
    reasons: list[str] = []
    if new_min < contract.min_replicas:
        reasons.append(f"new min {new_min} is below the contract floor {contract.min_replicas}")
    if new_max > contract.max_replicas:
        reasons.append(f"new max {new_max} is above the contract ceiling {contract.max_replicas}")
    if new_min > new_max:
        reasons.append(f"new min {new_min} is greater than new max {new_max}")
    if new_max < 1:
        reasons.append("max must be at least 1")
    if abs(new_min - current_min) > max_step or abs(new_max - current_max) > max_step:
        reasons.append(f"change is larger than the per-call step limit of {max_step} replicas")
    if len((reason or "").strip()) < 10:
        reasons.append("a reason of at least 10 characters is required; it goes into the audit log")
    if (new_min, new_max) == (current_min, current_max):
        reasons.append("no change: the app already runs with this range")

    allowed = not reasons
    mode = contract.effective_mode
    apply = allowed and not dry_run and writes_enabled and mode == "autonomous"
    if allowed and not apply:
        if dry_run:
            reasons.append("dry run: nothing was changed")
        elif not writes_enabled:
            reasons.append("writes are disabled on this server (ALLOW_WRITES is not true): proposal only")
        elif mode != "autonomous":
            reasons.append(f"contract mode is {mode}: proposal only, a human applies it")
    return ScaleDecision(allowed=allowed, apply=apply, mode=mode, reasons=reasons)
