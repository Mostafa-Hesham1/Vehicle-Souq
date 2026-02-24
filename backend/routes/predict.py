import pathlib
from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel
from fastai.vision.all import load_learner, PILImage
import io
import logging
import os
from pathlib import Path
import cv2  # Add OpenCV for YOLO
import numpy as np

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Relative path to the model - works on any OS
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = BASE_DIR / "densenet201_best_model.pkl"

# Global variable to hold the model
learn = None

# Workaround for the PosixPath issue on Windows
posix_backup = pathlib.PosixPath

try:
    # Cross-platform PosixPath workaround (needed when model was saved on Linux/Mac)
    pathlib.PosixPath = pathlib.WindowsPath
    
    # Load the model globally when the FastAPI app starts
    if MODEL_PATH.exists():
        learn = load_learner(MODEL_PATH)
        logging.info(f"Model loaded successfully from: {MODEL_PATH}")
    else:
        logging.error(f"Model file not found at: {MODEL_PATH}")
    
finally:
    # Restore the original PosixPath
    pathlib.PosixPath = posix_backup

class PredictionResponse(BaseModel):
    prediction: str
    probability: float

class YoloResponse(BaseModel):
    car_detected: bool

@router.post("/predict", response_model=PredictionResponse)
async def predict(file: UploadFile = File(...)):
    if learn is None:
        logging.error("Model is not loaded.")
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    try:
        img_content = await file.read()
        logging.info(f"Received file: {file.filename}")
        img = PILImage.create(io.BytesIO(img_content))

        pred, pred_idx, probs = learn.predict(img)

        logging.info(f"Prediction: {pred}, Probability: {probs[pred_idx]}")
        return PredictionResponse(prediction=str(pred), probability=float(probs[pred_idx]))
    except Exception as e:
        logging.error(f"An error occurred during prediction: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/yolo/check_car", response_model=YoloResponse)
async def check_car(file: UploadFile = File(...)):
    try:
        # Load YOLO model and configuration
        net = cv2.dnn.readNet("yolov3.weights", "yolov3.cfg")
        layer_names = net.getLayerNames()
        output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]

        img_content = await file.read()
        img_array = np.frombuffer(img_content, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        blob = cv2.dnn.blobFromImage(img, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
        net.setInput(blob)
        outs = net.forward(output_layers)

        
        car_detected = False
        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                if class_id == 2 and confidence > 0.5:  # Class ID 2 is for 'car' in COCO dataset
                    car_detected = True
                    break
            if car_detected:
                break

        return YoloResponse(car_detected=car_detected)
    except Exception as e:
        logging.error(f"An error occurred during YOLO detection: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
