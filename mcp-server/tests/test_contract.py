import pytest
from fakes import TAGS

from obsolete_mcp.contract import Contract, ContractError, evaluate_scale_request


def c(**over):
    return Contract.from_tags({**TAGS, **over})


def test_reads_tags():
    k = c()
    assert (k.min_replicas, k.max_replicas, k.change_mode, k.tier) == (1, 10, "autonomous", "nonprod")
    assert k.effective_mode == "autonomous"


def test_prod_is_always_review():
    assert c(**{"aiops-tier": "prod"}).effective_mode == "review"


@pytest.mark.parametrize("tags", [
    {"aiops-managed": "false"}, {"aiops-min-replicas": "x"}, {"aiops-change-mode": "yolo"},
    {"aiops-min-replicas": "5", "aiops-max-replicas": "2"}, {"aiops-tier": "staging"},
])
def test_bad_contracts(tags):
    with pytest.raises(ContractError):
        c(**tags)


def test_missing_tags():
    with pytest.raises(ContractError):
        Contract.from_tags({"aiops-managed": "true"})


def ev(k, new_min, new_max, **kw):
    args = dict(reason="pre-warm for the Monday 09:00 peak", writes_enabled=True, dry_run=False, max_step=5)
    args.update(kw)
    return evaluate_scale_request(k, 1, 10, new_min, new_max, **args)


def test_inside_envelope_applies_in_autonomous():
    d = ev(c(), 3, 10)
    assert d.allowed and d.apply


@pytest.mark.parametrize("lo,hi,text", [(0, 10, "below the contract floor"), (1, 11, "above the contract ceiling"),
                                        (6, 5, "greater than new max"), (1, 10, "no change")])
def test_rejections(lo, hi, text):
    d = ev(c(), lo, hi)
    assert not d.allowed and not d.apply and any(text in r for r in d.reasons)


def test_step_limit():
    d = ev(c(), 7, 10, max_step=5)
    assert not d.allowed and any("step limit" in r for r in d.reasons)


def test_reason_required():
    assert not ev(c(), 3, 10, reason="because").allowed


def test_review_mode_only_proposes():
    d = ev(c(**{"aiops-change-mode": "review"}), 3, 10)
    assert d.allowed and not d.apply and any("proposal only" in r for r in d.reasons)


def test_writes_disabled_only_proposes():
    d = ev(c(), 3, 10, writes_enabled=False)
    assert d.allowed and not d.apply


def test_dry_run_never_applies():
    d = ev(c(), 3, 10, dry_run=True)
    assert d.allowed and not d.apply
