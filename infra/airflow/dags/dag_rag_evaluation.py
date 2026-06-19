"""
RAG Evaluation DAG for Airflow.

This DAG runs RAG quality evaluations on evaluation datasets.
Following enterprise best practices:
- Minimal DAG file: Only orchestration logic
- Business logic in dag_tasks.py module
- Modular and testable: Tasks can be tested independently

DAG Flow:
1. Run evaluation on dataset items
2. Calculate metrics and update EvalRun record
3. Generate CSV report and save to S3
"""

from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# Import task functions from modular dag_tasks module
# These are imported from the mounted backend/src directory
# Volume mount: ../backend/src:/opt/airflow/primedata/src:ro
# PYTHONPATH: /opt/airflow/primedata/src
from primedata.evaluation.harness.dag_tasks import task_run_evaluation, task_generate_evaluation_report

# Define DAG
dag = DAG(
    'rag_quality_evaluation',
    default_args={
        'owner': 'primedata',
        'depends_on_past': False,
        'start_date': days_ago(1),
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 1,
        'retry_delay': timedelta(minutes=5),
    },
    description='RAG Quality Evaluation - Run evaluations on evaluation datasets',
    schedule_interval=None,  # Triggered manually
    catchup=False,
    tags=['primedata', 'rag', 'evaluation', 'quality'],
    params={
        'eval_run_id': None,  # Required parameter
        'dataset_id': None,  # Required parameter
        'product_id': None,  # Required parameter
        'version': None,  # Required parameter
        'workspace_id': None,  # Optional, will be looked up from product
    },
)

# Define tasks - minimal orchestration layer
evaluation_task = PythonOperator(
    task_id='run_evaluation',
    python_callable=task_run_evaluation,
    dag=dag,
    execution_timeout=timedelta(hours=2),  # Allow up to 2 hours for large datasets
)

report_task = PythonOperator(
    task_id='generate_report',
    python_callable=task_generate_evaluation_report,
    dag=dag,
)

# Set task dependencies
evaluation_task >> report_task

