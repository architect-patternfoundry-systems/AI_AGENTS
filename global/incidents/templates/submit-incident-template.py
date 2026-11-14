# templates/submit_incident.py
import sys
import os

# Align Python path with the DevOps Platform root
sys.path.insert(0, "/app")

from src.database import SessionLocal
from src.models import Incident, IncidentStatus

def submit():
    db = SessionLocal()
    try:
        incident = Incident(
            title="[System] Brief Description",
            status=IncidentStatus.RESOLVED,
            executive_summary="...",
            root_cause="...",
            customer_impact="...",
            lessons_learned="...",
            creator_email="agent@internal"
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)
        print(f"Incident created: {incident.id}")
    except Exception as e:
        db.rollback()
        print(f"Failed to submit incident: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    submit()
