-- Create Airflow database
CREATE DATABASE airflow;

-- Grant permissions to the primedata user
GRANT ALL PRIVILEGES ON DATABASE airflow TO primedata;
