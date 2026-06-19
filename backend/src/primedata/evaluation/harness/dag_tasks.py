"""
Airflow DAG Task Functions for RAG Evaluation.

This module contains task functions for Airflow DAGs that run RAG evaluations.
Following enterprise best practices:
- Separation of concerns: DAG orchestration vs business logic
- Modularity: Task functions are reusable and testable
- Maintainability: Business logic in one place, DAG files stay minimal
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from primedata.db.database import get_db
from primedata.db.models import EvalDataset, EvalDatasetItem, EvalRun, Product
from primedata.evaluation.harness.runner import EvaluationRunner
from primedata.indexing.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)
std_logger = logging.getLogger(__name__)  # For Airflow compatibility


def get_eval_dag_params(**context) -> Dict[str, Any]:
    """
    Extract and validate DAG parameters from Airflow context.

    Args:
        context: Airflow task context

    Returns:
        Dictionary with validated parameters (eval_run_id, dataset_id, product_id, version, etc.)
    """
    logger.info(f"Context keys: {list(context.keys())}")

    # Try to get parameters from DAG run conf first, then fall back to params
    dag_run = context.get("dag_run")
    if dag_run:
        logger.info(f"DAG run found: {dag_run.run_id}")
        if dag_run.conf:
            params = dag_run.conf
            logger.info(f"Using DAG run conf parameters: {params}")
        else:
            logger.warning("DAG run conf is empty")
            params = context.get("params", {})
            logger.info(f"Using default params: {params}")
    else:
        logger.warning("No DAG run found in context")
        params = context.get("params", {})
        logger.info(f"Using default params: {params}")

    # Get required parameters
    eval_run_id = params.get("eval_run_id")
    dataset_id = params.get("dataset_id")
    product_id = params.get("product_id")
    version = params.get("version")
    workspace_id = params.get("workspace_id")

    if not eval_run_id:
        raise ValueError("eval_run_id parameter is required")
    if not dataset_id:
        raise ValueError("dataset_id parameter is required")
    if not product_id:
        raise ValueError("product_id parameter is required")

    logger.info(
        f"Extracted parameters: eval_run_id={eval_run_id}, dataset_id={dataset_id}, "
        f"product_id={product_id}, version={version}"
    )

    return {
        "eval_run_id": UUID(eval_run_id),
        "dataset_id": UUID(dataset_id),
        "product_id": UUID(product_id),
        "version": version,
        "workspace_id": UUID(workspace_id) if workspace_id else None,
    }


def task_run_evaluation(**context) -> Dict[str, Any]:
    """
    Run RAG evaluation - called by Airflow DAG.

    This task:
    1. Extracts parameters from Airflow context
    2. Queries the database for the dataset and items
    3. Runs the evaluation using EvaluationRunner
    4. Updates the EvalRun record with results

    Args:
        context: Airflow task context

    Returns:
        Dictionary with task results
    """
    db = None
    try:
        # Extract parameters from context
        params = get_eval_dag_params(**context)
        eval_run_id = params["eval_run_id"]
        dataset_id = params["dataset_id"]
        product_id = params["product_id"]
        version = params["version"]
        workspace_id = params["workspace_id"]

        # Get database session
        db = next(get_db())

        # Get eval run record
        eval_run = db.query(EvalRun).filter(EvalRun.id == eval_run_id).first()
        if not eval_run:
            raise ValueError(f"EvalRun {eval_run_id} not found")

        # Get dataset from database (needed for logging and to populate fields)
        dataset = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Update status to running and ensure dataset_name and pipeline_version are set
        eval_run.status = "running"
        eval_run.started_at = datetime.utcnow()
        # Populate dataset_name and pipeline_version if not already set (for backward compatibility)
        if not eval_run.dataset_name:
            eval_run.dataset_name = dataset.name
        if eval_run.pipeline_version is None:
            eval_run.pipeline_version = version
        db.commit()

        logger.info("=" * 80)
        logger.info(f"Starting evaluation run {eval_run_id} for dataset {dataset_id}")
        logger.info(f"  Product ID: {product_id}")
        logger.info(f"  Version: {version}")
        logger.info(f"  Dataset: {dataset.name}")
        logger.info("=" * 80)

        # Get dataset items from database
        items = db.query(EvalDatasetItem).filter(EvalDatasetItem.dataset_id == dataset_id).all()
        if not items:
            raise ValueError(f"Dataset {dataset_id} has no items")

        logger.info(f"Loaded dataset {dataset.name} with {len(items)} items")

        # Get product for thresholds and config
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # Get thresholds from product config
        thresholds = product.rag_quality_thresholds or {}

        # Initialize runner with embedding generator
        embedding_config = product.embedding_config or {}
        model_name = embedding_config.get("embedder_name", "minilm")
        embedder = EmbeddingGenerator(
            model_name=model_name,
            workspace_id=product.workspace_id,
            db=db
        )

        runner = EvaluationRunner(db=db, embedding_generator=embedder)

        # Run evaluation
        completed_run = runner.run_evaluation(
            dataset_id=dataset_id,
            product_id=product_id,
            version=version,
            thresholds=thresholds,
        )

        # IMPORTANT: Update the original eval_run with metrics from completed_run
        # The runner might have updated a different eval_run, so we need to copy
        # the metrics to the one we're tracking in this DAG run
        if completed_run.id != eval_run_id:
            logger.warning(
                f"Runner updated different eval_run {completed_run.id} instead of {eval_run_id}. "
                f"Copying metrics to correct eval_run."
            )
        
        # Refresh the eval_run to get latest state
        db.refresh(eval_run)
        
        # Copy metrics and status from completed_run to our eval_run
        eval_run.metrics = completed_run.metrics
        eval_run.status = completed_run.status
        
        # Save metrics to S3 with date-partitioned structure
        if eval_run.metrics:
            from primedata.storage.minio_client import minio_client
            import json
            
            # Build S3 path with date partitioning: ws/{workspace_id}/prod/{product_id}/eval/v{version}/{year}/{month}/{day}/{eval_run_id}/metrics.json
            now = datetime.utcnow()
            s3_path = (
                f"ws/{workspace_id}/prod/{product_id}/eval/v{version}/"
                f"{now.year:04d}/{now.month:02d}/{now.day:02d}/"
                f"{eval_run_id}/metrics.json"
            )
            
            # Save metrics to S3
            bucket = "primedata-exports"
            key = s3_path
            metrics_json = json.dumps(eval_run.metrics, default=str, indent=2)
            
            try:
                minio_client.put_bytes(
                    bucket=bucket,
                    key=key,
                    data=metrics_json.encode('utf-8'),
                    content_type="application/json"
                )
                eval_run.metrics_path = s3_path
                logger.info(f"Saved evaluation metrics to S3: {s3_path}")
            except Exception as s3_error:
                logger.error(f"Failed to save metrics to S3: {s3_error}", exc_info=True)
                # Continue even if S3 save fails - metrics are still in DB
        
        eval_run.finished_at = datetime.utcnow()
        db.commit()

        logger.info("=" * 80)
        logger.info(f"Completed evaluation run {eval_run_id}")
        logger.info(f"  Items evaluated: {len(items)}")
        if eval_run.metrics and eval_run.metrics.get("aggregate"):
            logger.info(f"  Aggregate metrics: {len(eval_run.metrics['aggregate'])} metric types")
            for metric_name, metric_data in eval_run.metrics["aggregate"].items():
                if isinstance(metric_data, dict):
                    logger.info(f"    {metric_name}: mean={metric_data.get('mean', 0):.4f}, count={metric_data.get('count', 0)}")
        logger.info("=" * 80)

        return {
            "eval_run_id": str(eval_run_id),
            "status": "completed",
            "items_evaluated": len(items),
        }

    except Exception as e:
        logger.error(f"Evaluation run failed: {e}", exc_info=True)
        std_logger.error(f"Evaluation run failed: {e}", exc_info=True)

        # Update eval run status to failed
        if db:
            try:
                params = get_eval_dag_params(**context)
                eval_run_id = params["eval_run_id"]
                eval_run = db.query(EvalRun).filter(EvalRun.id == eval_run_id).first()
                if eval_run:
                    eval_run.status = "failed"
                    eval_run.finished_at = datetime.utcnow()
                    if eval_run.metrics is None:
                        eval_run.metrics = {}
                    eval_run.metrics["error"] = str(e)
                    db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update eval run status: {update_error}")

        raise

    finally:
        if db:
            db.close()


def task_generate_evaluation_report(**context) -> Dict[str, Any]:
    """
    Generate evaluation report (CSV) and save to S3.
    
    This task:
    1. Generates CSV report with all metrics
    2. Uploads to S3
    3. Updates EvalRun with report_path
    """
    import csv
    import io
    
    db = None
    try:
        params = get_eval_dag_params(**context)
        eval_run_id = params["eval_run_id"]
        product_id = params["product_id"]
        workspace_id = params["workspace_id"]
        
        if not workspace_id:
            # Get workspace_id from product if not provided
            db = next(get_db())
            product = db.query(Product).filter(Product.id == product_id).first()
            if product:
                workspace_id = product.workspace_id
            else:
                raise ValueError(f"Product {product_id} not found")
            db.close()
            db = None
        
        db = next(get_db())
        
        # Get eval run with metrics
        eval_run = db.query(EvalRun).filter(EvalRun.id == eval_run_id).first()
        if not eval_run:
            raise ValueError(f"EvalRun {eval_run_id} not found")
        
        if not eval_run.metrics:
            logger.warning(f"EvalRun {eval_run_id} has no metrics, skipping report generation")
            return {"status": "skipped", "reason": "no_metrics"}
        
        # Get product for metadata
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")
        
        # Generate CSV report
        csv_content = generate_csv_report(eval_run, product)
        
        # Get version from params (data version) - this should match the metrics path
        # The eval_run.version is the evaluation run version, but we need the data version
        # which was passed to the DAG in the conf
        version = params.get("version")
        if not version:
            # Fallback to eval_run.version if not in params
            version = eval_run.version
            logger.warning(f"Version not found in params, using eval_run.version: {version}")
        
        # Generate report path with date-partitioned structure
        # Structure: ws/{workspace_id}/prod/{product_id}/eval/v{version}/{year}/{month}/{day}/{eval_run_id}/report.csv
        now = datetime.utcnow()
        report_path = (
            f"ws/{workspace_id}/prod/{product_id}/eval/v{version}/"
            f"{now.year:04d}/{now.month:02d}/{now.day:02d}/"
            f"{eval_run_id}/report.csv"
        )
        
        # Upload to S3
        from primedata.storage.minio_client import minio_client
        
        bucket = "primedata-exports"
        key = report_path
        
        minio_client.put_bytes(
            bucket=bucket,
            key=key,
            data=csv_content.encode('utf-8'),
            content_type="text/csv"
        )
        
        logger.info(f"Uploaded CSV report to {report_path}")
        
        # Update eval run with report path
        eval_run.report_path = report_path
        eval_run.finished_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "success",
            "report_path": report_path,
        }
        
    except Exception as e:
        logger.error(f"Failed to generate report: {e}", exc_info=True)
        std_logger.error(f"Failed to generate report: {e}", exc_info=True)
        raise
    finally:
        if db:
            db.close()


def generate_csv_report(eval_run: EvalRun, product: Product) -> str:
    """Generate CSV report content."""
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header section
    writer.writerow(["RAG Quality Evaluation Report"])
    writer.writerow([])
    writer.writerow(["Evaluation Run ID", str(eval_run.id)])
    writer.writerow(["Product ID", str(eval_run.product_id)])
    writer.writerow(["Product Name", product.name if product else "N/A"])
    writer.writerow(["Version", eval_run.version])
    writer.writerow(["Dataset ID", str(eval_run.dataset_id)])
    writer.writerow(["Status", eval_run.status])
    writer.writerow(["Started At", eval_run.started_at.isoformat() + "Z" if eval_run.started_at else "N/A"])
    writer.writerow(["Finished At", eval_run.finished_at.isoformat() + "Z" if eval_run.finished_at else "N/A"])
    writer.writerow(["Generated At", datetime.utcnow().isoformat() + "Z"])
    writer.writerow([])
    
    # Aggregate metrics section
    metrics = eval_run.metrics or {}
    aggregate = metrics.get("aggregate", {})
    
    writer.writerow(["Aggregate Metrics"])
    writer.writerow(["Metric", "Mean", "Min", "Max", "Count"])
    
    for metric_name, metric_data in aggregate.items():
        if isinstance(metric_data, dict):
            writer.writerow([
                metric_name,
                f"{metric_data.get('mean', 0):.4f}",
                f"{metric_data.get('min', 0):.4f}",
                f"{metric_data.get('max', 0):.4f}",
                metric_data.get('count', 0)
            ])
    
    writer.writerow([])
    
    # Quality gates section (if thresholds exist)
    if product and product.rag_quality_thresholds:
        writer.writerow(["Quality Gates"])
        writer.writerow(["Metric", "Threshold", "Actual Mean", "Status"])
        
        thresholds = product.rag_quality_thresholds
        for metric_name, metric_data in aggregate.items():
            if isinstance(metric_data, dict):
                threshold_key = f"{metric_name}_min"
                threshold = thresholds.get(threshold_key, 0)
                actual = metric_data.get('mean', 0)
                status = "PASS" if actual >= threshold else "FAIL"
                
                writer.writerow([
                    metric_name,
                    f"{threshold:.4f}",
                    f"{actual:.4f}",
                    status
                ])
        
        writer.writerow([])
    
    # Per-query results section
    writer.writerow(["Per-Query Results"])
    per_query = metrics.get("per_query", [])
    
    if per_query:
        # Collect all metric names dynamically from all results
        all_metric_names = set()
        for result in per_query:
            if "error" not in result:
                item_metrics = result.get("metrics", {})
                all_metric_names.update(item_metrics.keys())
        
        # Sort metric names for consistent ordering
        # Put standard metrics first, then retrieval metrics
        standard_metrics = [
            "groundedness",
            "context_relevance",
            "answer_relevance",
            "answer_correctness",
            "citation_coverage",
            "refusal_correctness",
        ]
        sorted_metrics = []
        for metric in standard_metrics:
            if metric in all_metric_names:
                sorted_metrics.append(metric)
        for metric in sorted(all_metric_names):
            if metric not in standard_metrics:
                sorted_metrics.append(metric)
        
        # Write header
        header = ["Item ID", "Query", "Answer Method", "Retrieved Chunks Count"]
        header.extend([metric.replace("_", " ").title() for metric in sorted_metrics])
        header.append("Error")
        writer.writerow(header)
        
        # Write data rows
        for result in per_query:
            item_metrics = result.get("metrics", {})
            
            # Helper function to extract score safely
            def get_score(metric_name: str) -> str:
                metric = item_metrics.get(metric_name)
                if isinstance(metric, dict):
                    score = metric.get('score', 0)
                    return f"{score:.4f}"
                return "N/A"
            
            row = [
                result.get("item_id", ""),
                result.get("query", ""),
                result.get("answer_method", "N/A"),
                result.get("retrieved_chunks_count", 0),
            ]
            row.extend([get_score(metric_name) for metric_name in sorted_metrics])
            row.append(result.get("error", ""))
            writer.writerow(row)
    
    return output.getvalue()




