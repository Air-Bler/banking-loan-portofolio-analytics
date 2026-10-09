class DataUnavailable(Exception):
    """Databricks failed or timed out; the API answers 503 data_unavailable."""