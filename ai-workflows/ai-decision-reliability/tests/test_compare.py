import json

import pytest

from relia.compare import compare, main, protocol_template


def fixture():
    value = {"summary": {"ece": 0.02}, "count": 12,
             "dataset_sha256": "fixed-dataset", "empty": [],
             "gate_report": {"release_decision": "PASS", "gates": [
                 {"gate": "prohibited_field_access", "value": 0.0, "pass": True}]},
             "incremental_cycle": {"decision": "REJECT_UPDATE_KEEP_CURRENT_REFERENCE"}}
    source = json.dumps(value).encode()
    protocol = protocol_template(source)
    protocol.update(target_platform="test platform", rationale="Prespecified test-only fixture")
    protocol["tolerances"]["/summary/ece"] = {"abs": 0.001, "rel": 0}
    return value, source, protocol


def test_metric_difference_reports_within_and_outside_tolerance():
    value, source, protocol = fixture()
    value["summary"]["ece"] = 0.0205
    report = compare(source, json.dumps(value).encode(), protocol)
    assert report["pass"] and report["metrics"][-1]["difference"] > 0
    value["summary"]["ece"] = 0.022
    assert not compare(source, json.dumps(value).encode(), protocol)["pass"]


@pytest.mark.parametrize("change", ["decision", "gate", "count", "dataset", "missing", "extra", "type", "empty", "container"])
def test_exact_and_structural_changes_fail(change):
    value, source, protocol = fixture()
    if change == "decision":
        value["incremental_cycle"]["decision"] = "ACCEPT_UPDATE"
    elif change == "gate":
        value["gate_report"]["gates"][0]["pass"] = False
    elif change == "count":
        value["count"] = 11
    elif change == "dataset":
        value["dataset_sha256"] = "changed"
    elif change == "missing":
        del value["summary"]
    elif change == "extra":
        value["extra"] = 1
    elif change == "type":
        value["count"] = 12.0
    elif change == "container":
        value["gate_report"]["gates"] = {"0": value["gate_report"]["gates"][0]}
    else:
        value["empty"] = {}
    assert not compare(source, json.dumps(value).encode(), protocol)["pass"]


@pytest.mark.parametrize("change", ["unfilled", "missing", "extra", "negative", "infinite", "boolean", "counter", "reference", "platform"])
def test_invalid_or_incomplete_protocol_rejected(change):
    _, source, protocol = fixture()
    if change == "unfilled":
        protocol["tolerances"]["/summary/ece"]["abs"] = None
    elif change == "missing":
        del protocol["tolerances"]["/summary/ece"]
    elif change == "extra":
        protocol["tolerances"]["/count"] = {"abs": 1, "rel": 0}
    elif change in ("negative", "infinite", "boolean"):
        protocol["tolerances"]["/summary/ece"]["abs"] = {
            "negative": -1, "infinite": float("inf"), "boolean": True}[change]
    elif change == "counter":
        protocol["tolerances"]["/gate_report/gates/0/value"]["abs"] = 1
    elif change == "reference":
        protocol["reference_sha256"] = "wrong"
    else:
        protocol["target_platform"] = ""
    with pytest.raises(ValueError):
        compare(source, source, protocol)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_results_rejected(bad):
    value, source, protocol = fixture()
    value["summary"]["ece"] = bad
    with pytest.raises(ValueError, match="nonfinite"):
        compare(source, json.dumps(value).encode(), protocol)


def test_cli_template_refuses_overwrite_and_comparison_exit_codes(tmp_path, capsys):
    value, source, protocol = fixture()
    reference = tmp_path / "reference.json"
    actual = tmp_path / "actual.json"
    config = tmp_path / "protocol.json"
    reference.write_bytes(source)
    actual.write_bytes(source)
    assert main([str(reference), "--write-protocol-template", str(config)]) == 0
    with pytest.raises(SystemExit) as error:
        main([str(reference), "--write-protocol-template", str(config)])
    assert error.value.code == 2
    config.write_text(json.dumps(protocol))
    assert main([str(reference), str(actual), "--protocol", str(config)]) == 0
    value["gate_report"]["release_decision"] = "BLOCK"
    actual.write_text(json.dumps(value))
    assert main([str(reference), str(actual), "--protocol", str(config)]) == 1
