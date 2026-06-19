"""
PrimeData Pipeline DAG - Merged with AIRD Stages

Enterprise Best Practices:
- Minimal DAG file: Only orchestration logic
- Business logic in dag_tasks.py module
- Modular and testable: Tasks can be tested independently
- Maintainable: Changes to business logic don't require DAG file changes

Pipeline Flow:
1. Preprocess raw data (normalize, chunk, section) - requires raw files to exist
2. Score chunks (calculate trust metrics)
3. Generate fingerprint (aggregate metrics) | Validate (CSV) | Reporting (PDF) - parallel
4. Evaluate policy (check thresholds)
5. Index to Qdrant (embed and store with metadata)
6. Validate data quality (enterprise DQ rules)
7. Finalize (update product status)
"""

from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# Import task functions from modular dag_tasks module
# These are imported from the mounted backend/src directory
# Volume mount: ../backend/src:/opt/airflow/primedata/src:ro
# PYTHONPATH: /opt/airflow/primedata/src
from primedata.ingestion_pipeline.dag_tasks import (
    task_preprocess,
    task_scoring,
    task_fingerprint,
    task_validation,
    task_policy,
    task_reporting,
    task_indexing,
    task_validate_data_quality,
    task_finalize,
)

# Define DAG
dag = DAG(
    'data_ingestion_pipeline',
    default_args={
        'owner': 'primedata',
        'depends_on_past': False,
        'start_date': days_ago(1),
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 1,
        'retry_delay': timedelta(minutes=5),
    },
    description='PrimeData Pipeline - Merged with AIRD Stages (Modular Architecture)',
    schedule_interval=None,  # Triggered manually
    catchup=False,
    tags=['primedata', 'pipeline', 'aird', 'modular'],
)

# Define tasks - minimal orchestration layer
preprocess_task = PythonOperator(
    task_id='preprocess',
    python_callable=task_preprocess,
    dag=dag,
)

scoring_task = PythonOperator(
    task_id='scoring',
    python_callable=task_scoring,
    dag=dag,
)

fingerprint_task = PythonOperator(
    task_id='fingerprint',
    python_callable=task_fingerprint,
    dag=dag,
)

validation_task = PythonOperator(
    task_id='validation',
    python_callable=task_validation,
    dag=dag,
)

policy_task = PythonOperator(
    task_id='policy',
    python_callable=task_policy,
    dag=dag,
)

reporting_task = PythonOperator(
    task_id='reporting',
    python_callable=task_reporting,
    dag=dag,
)

indexing_task = PythonOperator(
    task_id='indexing',
    python_callable=task_indexing,
    execution_timeout=timedelta(hours=2),  # Allow up to 2 hours for large models
    dag=dag,
)

validate_data_quality_task = PythonOperator(
    task_id='validate_data_quality',
    python_callable=task_validate_data_quality,
    trigger_rule='none_failed_min_one_success',
    dag=dag,
)

finalize_task = PythonOperator(
    task_id='finalize',
    python_callable=task_finalize,
    dag=dag,
)

# Define task dependencies
# Flow: preprocess -> scoring -> [fingerprint, validation, reporting (parallel)]
#       fingerprint -> policy
#       [validation, reporting, policy] -> indexing -> validate_data_quality -> finalize
# Note: indexing task handles skip logic internally if vector_creation_enabled is False
preprocess_task >> scoring_task
scoring_task >> [fingerprint_task, validation_task, reporting_task]
fingerprint_task >> policy_task
[validation_task, reporting_task, policy_task] >> indexing_task
indexing_task >> validate_data_quality_task
validate_data_quality_task >> finalize_task
