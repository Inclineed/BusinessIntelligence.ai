from datetime import datetime
from unittest.mock import MagicMock

from engines.kpi_store import _execute_kpi_query

def test_execute_kpi_query_filters_incomplete_trailing_bucket():
    db_conn = MagicMock()
    cur = MagicMock()
    db_conn.cursor.return_value.__enter__.return_value = cur
    
    # Simulate a query returning three buckets:
    # 13:00, 14:00, 15:00
    # window_end is 15:00:00, so the 15:00 bucket is incomplete
    cur.fetchall.return_value = [
        (datetime(2024, 1, 15, 13, 0, 0), 100),
        (datetime(2024, 1, 15, 14, 0, 0), 120),
        (datetime(2024, 1, 15, 15, 0, 0), 2)  # Incomplete trailing bucket
    ]
    
    window_end = datetime(2024, 1, 15, 15, 0, 0)
    
    valid_rows = _execute_kpi_query(
        kpi_id="hourly_revenue",
        grain="hourly",
        query="SELECT 1",
        scenario_id="INC_005",
        window_start=datetime(2024, 1, 15, 0, 0, 0),
        window_end=window_end,
        db_conn=db_conn
    )
    
    assert len(valid_rows) == 2
    assert valid_rows[0][0] == datetime(2024, 1, 15, 13, 0, 0)
    assert valid_rows[1][0] == datetime(2024, 1, 15, 14, 0, 0)
