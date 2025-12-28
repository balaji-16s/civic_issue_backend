from pydantic import BaseModel

class Issue(BaseModel):
    description: str
    latitude: float
    longitude: float
