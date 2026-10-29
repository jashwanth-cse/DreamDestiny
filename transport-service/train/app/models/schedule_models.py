"""
Train Schedule Domain Models & Response Schemas
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RouteStop(BaseModel):
    """Normalized intermediate stop along a train route."""
    stop_number: int = Field(..., description="Chronological sequence number of the stop along the route")
    station_name: str = Field(..., description="Full station name")
    station_code: str = Field(..., description="Standard IRCTC station code, e.g. NDLS")
    arrival_time: str = Field(..., description="Arrival time HH:MM (normalized from SOURCE if origin)")
    departure_time: str = Field(..., description="Departure time HH:MM (normalized from DESTINATION if terminus)")
    halt_minutes: int = Field(..., description="Halt duration in minutes (0 for origin/destination)")
    day: int = Field(..., description="Journey day count starting at 1 from origin")
    distance_from_origin_km: int = Field(..., description="Cumulative distance in kilometers from origin")
    expected_platform: Optional[str] = Field(None, description="Expected platform number or None if unavailable")


class TrainScheduleData(BaseModel):
    """Full normalized train schedule details."""
    train_no: str = Field(..., description="4 or 5 digit train number")
    train_name: str = Field(..., description="Official train name")
    train_type: str = Field(..., description="Train category e.g. Superfast, Mail/Express")
    source_station_name: str = Field(..., description="Origin station name")
    source_station_code: str = Field(..., description="Origin station code")
    destination_station_name: str = Field(..., description="Destination station name")
    destination_station_code: str = Field(..., description="Destination station code")
    days_of_run: Dict[str, bool] = Field(
        ...,
        description="Weekly operation map e.g. {'Mon': True, 'Tue': True...}"
    )
    classes: List[str] = Field(..., description="Available travel classes on this train e.g. ['3A', 'SL']")
    total_duration_minutes: int = Field(..., description="Total journey duration in minutes")
    total_distance_km: int = Field(..., description="Total journey distance in kilometers")
    total_stops: int = Field(..., description="Total number of scheduled intermediate stops")
    schedule: List[RouteStop] = Field(..., description="Chronologically ordered route stops")


class TrainScheduleResponse(BaseModel):
    """API envelope response for train schedule endpoint."""
    success: bool = Field(True, description="Indicates request success")
    message: str = Field("Train schedule retrieved successfully", description="Status or detail message")
    data: TrainScheduleData = Field(..., description="Detailed train schedule data")
