from datetime import datetime

def calculate_days(start_date_str, end_date_str):
    start = datetime.fromisoformat(start_date_str).date()
    end = datetime.fromisoformat(end_date_str).date()
    if end < start:
        raise ValueError("end_date cannot be before start_date")
    return (end - start).days + 1
