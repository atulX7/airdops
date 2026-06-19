import uuid

from primedata.db.models import PipelineRun
from primedata.ingestion_pipeline.dag_tasks import task_decide_vector_indexing, task_record_vectors_skipped
from primedata.ingestion_pipeline.pipeline_config import resolve_effective_pipeline_config


class DummyDagRun:
    def __init__(self, conf):
        self.conf = conf
        self.run_id = "test-run"


def test_resolve_effective_pipeline_config_prefers_pipeline_run(db_session, test_product, test_workspace):
    pipeline_run = PipelineRun(
        workspace_id=test_workspace.id,
        product_id=test_product.id,
        version=1,
        dag_run_id="dag-run",
        metrics={
            "chunking_config": {
                "resolved_settings": {
                    "chunk_size": 777,
                    "chunk_overlap": 77,
                    "chunking_strategy": "semantic",
                    "confidence": 0.9,
                }
            }
        },
    )
    db_session.add(pipeline_run)

    test_product.chunking_config = {
        "mode": "auto",
        "resolved_settings": {"chunk_size": 999, "chunk_overlap": 99, "chunking_strategy": "fixed_size"},
        "auto_settings": {"confidence_threshold": 0.7},
    }
    db_session.commit()

    effective_preprocess = resolve_effective_pipeline_config(test_product, {}, pipeline_run)
    effective_scoring = resolve_effective_pipeline_config(test_product, {}, pipeline_run)

    resolved_settings = effective_preprocess["chunking_config"]["resolved_settings"]
    assert resolved_settings["chunk_size"] == 777
    assert resolved_settings["source"] == "pipeline_run"
    assert effective_scoring["chunking_config"]["resolved_settings"] == resolved_settings


def test_playbook_selection_not_overwritten_without_manual_choice(db_session, test_product):
    test_product.playbook_id = "AUTO"
    test_product.playbook_selection = {
        "method": "auto_detected",
        "playbook_id": "AUTO",
        "reason": "detected",
    }
    db_session.commit()

    effective = resolve_effective_pipeline_config(
        test_product,
        {"playbook_id": "MANUAL"},
        pipeline_run=None,
    )

    assert effective["playbook_selection"]["method"] == "auto_detected"


def test_vector_gate_skips_indexing_and_records_metrics(db_session, test_product, test_workspace):
    test_product.vector_creation_enabled = False
    pipeline_run = PipelineRun(
        workspace_id=test_workspace.id,
        product_id=test_product.id,
        version=1,
        dag_run_id=str(uuid.uuid4()),
    )
    db_session.add(pipeline_run)
    db_session.commit()

    context = {
        "dag_run": DummyDagRun(
            {
                "workspace_id": str(test_workspace.id),
                "product_id": str(test_product.id),
                "version": 1,
            }
        )
    }

    assert task_decide_vector_indexing(**context) == "skip_indexing"
    task_record_vectors_skipped(**context)

    db_session.refresh(pipeline_run)
    assert pipeline_run.metrics["vectors_skipped"] is True
