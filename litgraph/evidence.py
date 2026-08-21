from __future__ import annotations

import re
from typing import Any

FIELD_TYPES = {
    "text", "number", "boolean", "date", "single_choice", "multi_choice",
    "citation", "url", "range", "table",
}
VERIFICATION_STATES = {"suggested", "confirmed", "rejected"}
EXTRACTION_METHODS = {"manual", "imported", "automatic"}

BUILTIN_SCHEMAS = [
    {
        "id": "generic_research", "name": "Generic Research",
        "description": "Field-independent characterization of a research paper.",
        "fields": [
            ("research_question", "Research question", "text", ""),
            ("hypothesis", "Hypothesis", "text", ""),
            ("methodology", "Methodology", "text", ""),
            ("study_type", "Study type", "text", ""),
            ("dataset_sample", "Dataset or sample", "text", ""),
            ("experimental_setup", "Experimental setup", "text", ""),
            ("variables", "Variables", "text", ""),
            ("evaluation_metrics", "Evaluation metrics", "text", ""),
            ("baselines", "Baselines", "text", ""),
            ("main_findings", "Main findings", "text", ""),
            ("limitations", "Limitations", "text", ""),
            ("threats_to_validity", "Threats to validity", "text", ""),
            ("future_work", "Future work", "text", ""),
            ("artifact_links", "Software, data, and artifacts", "url", ""),
        ],
    },
    {
        "id": "machine_learning", "name": "Machine Learning",
        "description": "Models, training, datasets, and evaluation details.",
        "fields": [
            ("task", "Task", "text", ""), ("model", "Model or architecture", "text", ""),
            ("training_method", "Training method", "text", ""), ("dataset", "Dataset", "text", ""),
            ("precision", "Numerical precision", "text", ""), ("metrics", "Reported metrics", "table", ""),
            ("compute_budget", "Compute budget", "text", ""), ("baseline_models", "Baseline models", "text", ""),
        ],
    },
    {
        "id": "hardware_accelerators", "name": "Hardware Accelerators",
        "description": "Optional architecture, implementation, and efficiency characterization.",
        "fields": [
            ("accelerator_type", "Accelerator type", "single_choice", "digital|analog|mixed-signal|CIM/PIM|near-memory"),
            ("device", "Memory or device technology", "text", ""), ("technology_node", "Technology node", "number", "nm"),
            ("supply_voltage", "Supply voltage", "number", "V"), ("array_size", "Array size", "text", ""),
            ("cell_precision", "Cell precision", "number", "bit"), ("converter_resolution", "ADC/DAC resolution", "text", ""),
            ("dataflow", "Dataflow and mapping", "text", ""), ("workload", "Workload", "text", ""),
            ("throughput", "Throughput", "number", "TOPS"), ("latency", "Latency", "number", "s"),
            ("energy_efficiency", "Energy efficiency", "number", "TOPS/W"), ("area", "Area", "number", "mm²"),
            ("accuracy_degradation", "Accuracy degradation", "number", "%"),
            ("nonideality_model", "Noise or nonideality model", "text", ""),
            ("mitigation", "Calibration or mitigation", "text", ""),
            ("evaluation_basis", "Evaluation basis", "single_choice", "simulation|post-layout|FPGA|silicon measurement"),
        ],
    },
    {
        "id": "clinical_study", "name": "Clinical Study",
        "description": "Population, intervention, comparison, outcomes, and study design.",
        "fields": [
            ("population", "Population", "text", ""), ("intervention", "Intervention", "text", ""),
            ("comparison", "Comparison or control", "text", ""), ("outcomes", "Outcomes", "text", ""),
            ("study_design", "Study design", "text", ""), ("sample_size", "Sample size", "number", "participants"),
            ("follow_up", "Follow-up period", "text", ""), ("effect_size", "Effect size", "text", ""),
        ],
    },
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:60] or "field"


def validate_field(field: dict[str, Any]) -> dict[str, Any]:
    label = str(field.get("label", "")).strip()
    field_type = str(field.get("type", "text"))
    if not label or len(label) > 120:
        raise ValueError("Every field needs a label of at most 120 characters")
    if field_type not in FIELD_TYPES:
        raise ValueError(f"Unsupported evidence field type: {field_type}")
    options = field.get("options", [])
    if isinstance(options, str):
        options = [option.strip() for option in options.split("|") if option.strip()]
    if not isinstance(options, list) or any(not isinstance(option, str) for option in options):
        raise ValueError("Field options must be a list of text values")
    return {
        "id": str(field.get("id", "")).strip(), "key": slugify(str(field.get("key") or label)),
        "label": label, "type": field_type, "unit": str(field.get("unit", "")).strip()[:40],
        "options": options[:100], "group_name": str(field.get("group", "")).strip()[:80],
    }


def validate_evidence_value(field_type: str, value: Any) -> Any:
    if value in (None, "", []):
        return None
    if field_type == "number":
        return float(value)
    if field_type == "boolean":
        if value not in (True, False):
            raise ValueError("Boolean evidence must be true or false")
        return value
    if field_type == "range":
        if not isinstance(value, dict) or "min" not in value or "max" not in value:
            raise ValueError("A range requires minimum and maximum values")
        return {"min": float(value["min"]), "max": float(value["max"]), "uncertainty": value.get("uncertainty")}
    if field_type == "multi_choice":
        if not isinstance(value, list):
            raise ValueError("Multiple-choice evidence must be a list")
        return [str(item) for item in value]
    return str(value)[:20_000]

