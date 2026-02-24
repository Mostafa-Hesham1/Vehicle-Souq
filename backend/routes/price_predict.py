from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
import pickle
import os
from pathlib import Path
import pandas as pd

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Relative paths - works on any OS
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = BASE_DIR / "ML-Models" / "Price-predection" / "PricePredection-1-.pkl"
SCALER_PATH = BASE_DIR / "ML-Models" / "Price-predection" / "scaler (1).pkl"
ENCODERS_PATH = BASE_DIR / "ML-Models" / "Price-predection" / "label_encoders.pkl"

with open(MODEL_PATH, 'rb') as model_file:
    best_model = pickle.load(model_file)
with open(SCALER_PATH, 'rb') as scaler_file:
    scaler = pickle.load(scaler_file)
with open(ENCODERS_PATH, 'rb') as encoders_file:
    label_encoders = pickle.load(encoders_file)

logging.info(f"Model, scaler, and label encoders loaded successfully from: {MODEL_PATH}, {SCALER_PATH}, {ENCODERS_PATH}")

class CarData(BaseModel):
    Make: str
    Model: str
    BodyType: str
    Color: str
    Kilometers: int
    Year: int
    FuelType: str
    TransmissionType: str
    CC: int
    location: str
    listBy: str

@router.post("/predict_price")
async def predict_price(car_data: CarData):
    try:
        # Replace this with your actual prediction logic
        predicted_price = predict_car_price(car_data.dict())
        return {"predicted_price": predicted_price}
    except Exception as e:
        logging.error(f"An error occurred during price prediction: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

def predict_car_price(car_data):
    # Convert input to DataFrame
    car_df = pd.DataFrame([car_data])

    # Encode categorical variables
    for col, le in label_encoders.items():
        if col in car_df:
            car_df[col] = car_df[col].apply(lambda x: le.transform([x])[0] if x in le.classes_ else -1)

    # Scale the features
    car_scaled = scaler.transform(car_df)

    # Predict price
    predicted_price = best_model.predict(car_scaled)
    return float(predicted_price[0]) - 150000# Convert numpy.float32 to standard Python float
