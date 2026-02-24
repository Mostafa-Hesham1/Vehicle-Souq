from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from ultralytics import YOLO
import numpy as np
import cv2
import base64
import os
import logging
import traceback
from PIL import Image
import io
import torch
import torch.nn as nn
from typing import List, Dict, Union, Optional
import sys
import requests  # Add this import at the top

# Add torchvision imports for Mask R-CNN
import torchvision
from torchvision.models.detection import maskrcnn_resnet50_fpn_v2
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
import torchvision.transforms as T
from torchvision.models.detection.anchor_utils import AnchorGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the mmdetection path if not already in sys.path - relative to this file
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mmdet_path = os.path.join(_BASE_DIR, "mmdetection")
if mmdet_path not in sys.path:
    sys.path.append(mmdet_path)

# Only import mmdetection libraries if available
try:
    from mmdet.apis import inference_detector, init_detector
    from mmengine import Config
    mmdet_available = True
    logger.info("MMDetection libraries successfully imported")
except ImportError as e:
    mmdet_available = False
    logger.error(f"MMDetection import error: {str(e)}")
    logger.warning("MMDetection not available. DCN+ model will not be loaded.")

# Define the OptimizedCarDamageModel class
class OptimizedCarDamageModel(nn.Module):
    def __init__(self, num_classes=7):
        super().__init__()
        self.model = maskrcnn_resnet50_fpn_v2(weights="DEFAULT")
        
        # Add anchor generator configuration from your notebook
        anchor_generator = AnchorGenerator(
            sizes=((16,), (32,), (64,), (128,), (256,)), 
            aspect_ratios=((0.5, 1.0, 2.0),) * 5
        )
        self.model.rpn.anchor_generator = anchor_generator
        self.model.rpn.pre_nms_top_n_train = 3000
        self.model.rpn.post_nms_top_n_train = 1500
        self.model.rpn.pre_nms_top_n_test = 1500
        self.model.rpn.post_nms_top_n_test = 750
        self.model.rpn.nms_thresh = 0.6
        self.model.roi_heads.nms_thresh = 0.4
        self.model.roi_heads.score_thresh = 0.1
        self.model.roi_heads.detections_per_img = 300
        
        # Replace the classifier with a new one for our specific number of classes
        in_features = self.model.roi_heads.box_predictor.cls_score.in_features
        self.model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
        
        # Replace the mask predictor
        in_features_mask = self.model.roi_heads.mask_predictor.conv5_mask.in_channels
        self.model.roi_heads.mask_predictor = MaskRCNNPredictor(in_features_mask, 256, num_classes)
    
    def forward(self, images, targets=None):
        return self.model(images, targets)

router = APIRouter()
# Relative paths to the models - works on any OS
_MODELS_DIR = os.path.join(_BASE_DIR, "ML-Models", "CarDamageModels")
YOLO_MODEL_PATH = os.path.join(_MODELS_DIR, "yolov8l_seg_car_damage.pt")
DCN_CONFIG_PATH = os.path.join(_MODELS_DIR, "dcn_plus_cfg.py")
DCN_CHECKPOINT_PATH = os.path.join(_MODELS_DIR, "epoch_25_copy.pth")
MASKRCNN_MODEL_PATH = os.path.join(_MODELS_DIR, "combined_cardamage_model.pt")

# Define the class names and color mapping for visualization
CLASS_NAMES = ['dent', 'scratch', 'crack', 'glass shatter', 'lamp broken', 'tire flat']

# Color mapping in BGR format (for OpenCV)
COLOR_MAPPING = {
    0: (0, 0, 255),     # dent - red
    1: (0, 255, 0),     # scratch - green
    2: (255, 0, 0),     # crack - blue
    3: (0, 255, 255),   # glass shatter - yellow
    4: (255, 0, 255),   # lamp broken - magenta
    5: (255, 255, 0)    # tire flat - cyan
}

# Initialize the models
yolo_model = None
dcn_model = None
maskrcnn_model = None

try:
    # YOLO Damage detection model
    yolo_model = YOLO(YOLO_MODEL_PATH)
    logger.info(f"YOLO car damage segmentation model loaded successfully from: {YOLO_MODEL_PATH}")
except Exception as e:
    logger.error(f"Failed to load YOLO model: {e}")

# Load Mask R-CNN model
try:
    logger.info(f"Attempting to load Mask R-CNN model from: {MASKRCNN_MODEL_PATH}")
    
    # Check if the model file exists
    if not os.path.exists(MASKRCNN_MODEL_PATH):
        logger.error(f"Mask R-CNN model file does not exist at: {MASKRCNN_MODEL_PATH}")
    else:
        logger.info("Mask R-CNN model file exists")
        
        # Initialize the model with 7 classes (background + 6 damage types)
        device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Using device: {device} for Mask R-CNN model")
        
        maskrcnn_model = OptimizedCarDamageModel(num_classes=7)  # 6 damage classes + background
        
        # Load the trained weights using the same format as your notebook
        checkpoint = torch.load(MASKRCNN_MODEL_PATH, map_location=device)
        if 'model_state_dict' in checkpoint:
            maskrcnn_model.load_state_dict(checkpoint['model_state_dict'])
        else:
            maskrcnn_model.load_state_dict(checkpoint)
        
        # Set to evaluation mode and move to device
        maskrcnn_model.eval()
        maskrcnn_model.to(device)
        
        # Ensure the model is in evaluation mode
        maskrcnn_model.training = False
        
        logger.info(f"Mask R-CNN car damage detection model loaded successfully from: {MASKRCNN_MODEL_PATH}")
        
except Exception as e:
    logger.error(f"Failed to load Mask R-CNN model: {e}")
    logger.error(f"Error traceback: {traceback.format_exc()}")

if mmdet_available:
    try:
        # DCN+ model - more debugging information
        logger.info(f"Attempting to load DCN+ model from config: {DCN_CONFIG_PATH}")
        logger.info(f"Checkpoint path: {DCN_CHECKPOINT_PATH}")
        
        # Check if the config file exists
        if not os.path.exists(DCN_CONFIG_PATH):
            logger.error(f"DCN+ config file does not exist at: {DCN_CONFIG_PATH}")
        else:
            logger.info("DCN+ config file exists")
            
        # Check if the checkpoint file exists
        if not os.path.exists(DCN_CHECKPOINT_PATH):
            logger.error(f"DCN+ checkpoint file does not exist at: {DCN_CHECKPOINT_PATH}")
        else:
            logger.info("DCN+ checkpoint file exists")
        
        # Try to load the model with more specific error handling
        try:
            # First load the config file directly
            cfg = Config.fromfile(DCN_CONFIG_PATH)
            logger.info("DCN+ config file loaded successfully")
            
            # Next try to initialize the model with the config and checkpoint
            device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
            logger.info(f"Using device: {device} for DCN+ model")
            
            dcn_model = init_detector(DCN_CONFIG_PATH, DCN_CHECKPOINT_PATH, device=device)
            logger.info(f"DCN+ car damage detection model loaded successfully from: {DCN_CHECKPOINT_PATH}")
        except Exception as detailed_err:
            logger.error(f"Error during DCN+ model initialization: {detailed_err}")
            logger.error(f"Error traceback: {traceback.format_exc()}")
            
    except Exception as e:
        logger.error(f"Failed to load DCN+ model: {e}")
        logger.error(f"Error traceback: {traceback.format_exc()}")

# Try to initialize the Mask R-CNN model
try:
    num_classes = len(CLASS_NAMES)
    mask_rcnn_model = OptimizedCarDamageModel(num_classes=num_classes)
    
    # Load the weights for the Mask R-CNN model if available
    mask_rcnn_weights_path = r"C:\Users\mosta\OneDrive\Desktop\VehicleSouq (2)\VehicleSouq\backend\ML-Models\CarDamageModels\mask_rcnn_weights.pth"
    if os.path.exists(mask_rcnn_weights_path):
        mask_rcnn_model.load_state_dict(torch.load(mask_rcnn_weights_path, map_location='cpu'))
        logger.info(f"Mask R-CNN model weights loaded successfully from: {mask_rcnn_weights_path}")
    else:
        logger.warning(f"Mask R-CNN weights file not found at: {mask_rcnn_weights_path}. Mask R-CNN model will not be used.")
except Exception as e:
    logger.error(f"Failed to initialize Mask R-CNN model: {e}")
    logger.error(f"Error traceback: {traceback.format_exc()}")

def preprocess_image(img, reduce_reflection=False, enhance_contrast=False):
    """
    Improved preprocessing with better reflection handling
    """
    # Convert to valid format
    if img.max() <= 1.0:
        img = (img * 255).astype(np.uint8)
    
    # Make a copy of the original image
    processed_img = img.copy()
    
    # Step 1: Advanced reflection reduction if requested
    if reduce_reflection:
        processed_img = reduce_sun_reflections(processed_img)
    
    # Step 2: Enhanced contrast if requested
    if enhance_contrast:
        processed_img = enhance_image_contrast(processed_img)
    
    return processed_img

def reduce_sun_reflections(img):
    """
    Advanced sun reflection reduction that preserves car details
    """
    # Convert to different color spaces for better reflection detection
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    
    h, s, v = cv2.split(img_hsv)
    l, a, b = cv2.split(img_lab)
    
    # Method 1: Detect overexposed areas (sun reflections)
    # More conservative thresholds to avoid removing car details
    bright_mask = (v > 240) & (s < 40)  # Very bright and low saturation
    
    # Method 2: Detect specular highlights using LAB color space
    # High L value with low a,b variation indicates specular reflection
    specular_mask = (l > 220) & (np.abs(a - 128) < 15) & (np.abs(b - 128) < 15)
    
    # Method 3: Detect white/silvery reflections
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    white_mask = (gray > 230) & (s < 25)
    
    # Combine all reflection masks
    reflection_mask = bright_mask | specular_mask | white_mask
    
    # Apply morphological operations to clean up the mask
    kernel_small = np.ones((3, 3), np.uint8)
    kernel_medium = np.ones((5, 5), np.uint8)
    
    # Remove small noise
    reflection_mask = cv2.morphologyEx(reflection_mask.astype(np.uint8), cv2.MORPH_OPEN, kernel_small)
    
    # Close gaps in reflection areas
    reflection_mask = cv2.morphologyEx(reflection_mask, cv2.MORPH_CLOSE, kernel_medium)
    
    # Ensure we only process significant reflection areas (filter out tiny spots)
    contours, _ = cv2.findContours(reflection_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered_mask = np.zeros_like(reflection_mask)
    
    min_area = img.shape[0] * img.shape[1] * 0.001  # At least 0.1% of image area
    for contour in contours:
        if cv2.contourArea(contour) > min_area:
            cv2.fillPoly(filtered_mask, [contour], 255)
    
    reflection_mask = filtered_mask
    
    # Apply different techniques based on reflection intensity
    result_img = img.copy()
    
    if np.sum(reflection_mask) > 0:  # Only process if reflections detected
        # Method 1: Inpainting for small, intense reflections
        intense_reflections = (v > 250) & (reflection_mask > 0)
        intense_reflections = cv2.morphologyEx(intense_reflections.astype(np.uint8), cv2.MORPH_OPEN, kernel_small)
        
        if np.sum(intense_reflections) > 0:
            result_img = cv2.inpaint(result_img, intense_reflections, 3, cv2.INPAINT_TELEA)
        
        # Method 2: Selective histogram matching for moderate reflections
        moderate_reflections = reflection_mask & (~intense_reflections)
        
        if np.sum(moderate_reflections) > 0:
            # Create a mask of surrounding non-reflection areas for reference
            dilated_mask = cv2.dilate(moderate_reflections, np.ones((15, 15), np.uint8), iterations=1)
            reference_mask = dilated_mask & (~reflection_mask)
            
            if np.sum(reference_mask) > 0:
                # Apply adaptive histogram equalization to reflection areas
                result_img_lab = cv2.cvtColor(result_img, cv2.COLOR_BGR2LAB)
                l_channel = result_img_lab[:, :, 0]
                
                # Get statistics from reference areas
                ref_mean = np.mean(l_channel[reference_mask > 0])
                ref_std = np.std(l_channel[reference_mask > 0])
                
                # Adjust reflection areas to match reference statistics
                reflection_areas = moderate_reflections > 0
                current_mean = np.mean(l_channel[reflection_areas])
                current_std = np.std(l_channel[reflection_areas])
                
                if current_std > 0:
                    # Normalize and scale to match reference
                    normalized = (l_channel[reflection_areas] - current_mean) / current_std
                    adjusted = normalized * ref_std + ref_mean
                    adjusted = np.clip(adjusted, 0, 255)
                    
                    l_channel[reflection_areas] = adjusted
                    result_img_lab[:, :, 0] = l_channel
                    result_img = cv2.cvtColor(result_img_lab, cv2.COLOR_LAB2BGR)
        
        # Method 3: Gentle bilateral filtering for overall smoothing
        result_img = cv2.bilateralFilter(result_img, 5, 50, 50)
    
    return result_img

def enhance_image_contrast(img):
    """
    Enhanced contrast improvement that preserves natural appearance
    """
    # Convert to LAB color space for better contrast control
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Apply adaptive histogram equalization to L channel
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)
    
    # Gently enhance edges without creating artifacts
    edge_enhanced = cv2.addWeighted(l_enhanced, 0.9, cv2.Laplacian(l_enhanced, cv2.CV_8U), 0.1, 0)
    edge_enhanced = np.clip(edge_enhanced, 0, 255).astype(np.uint8)
    
    # Merge back
    enhanced_lab = cv2.merge((edge_enhanced, a, b))
    enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    
    # Apply subtle unsharp masking for detail enhancement
    gaussian = cv2.GaussianBlur(enhanced_img, (0, 0), 1.0)
    unsharp_mask = cv2.addWeighted(enhanced_img, 1.3, gaussian, -0.3, 0)
    
    return np.clip(unsharp_mask, 0, 255).astype(np.uint8)

def preprocess_image_maskrcnn(img, reduce_reflection=False, enhance_contrast=False):
    """
    Advanced preprocessing specifically for Mask R-CNN with improved reflection handling
    """
    # Convert to valid format
    if img.max() <= 1.0:
        img = (img * 255).astype(np.uint8)
    
    # Make a copy of the original image
    processed_img = img.copy()
    
    # Step 1: Gentle noise reduction that preserves edges
    processed_img = cv2.bilateralFilter(processed_img, 7, 50, 50)
    
    # Step 2: Advanced reflection reduction if requested
    if reduce_reflection:
        processed_img = reduce_sun_reflections_maskrcnn(processed_img)
    
    # Step 3: Enhanced contrast for better damage visibility
    if enhance_contrast:
        processed_img = enhance_contrast_maskrcnn(processed_img)
    
    # Step 4: Subtle sharpening for damage detail enhancement
    kernel = np.array([[-0.5, -0.5, -0.5], [-0.5, 5.0, -0.5], [-0.5, -0.5, -0.5]])
    sharpened = cv2.filter2D(processed_img, -1, kernel)
    processed_img = cv2.addWeighted(processed_img, 0.8, sharpened, 0.2, 0)
    processed_img = np.clip(processed_img, 0, 255).astype(np.uint8)
    
    return processed_img

def reduce_sun_reflections_maskrcnn(img):
    """
    Specialized reflection reduction for Mask R-CNN that preserves damage features
    """
    # Multi-scale reflection detection
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    
    h, s, v = cv2.split(img_hsv)
    l, a, b = cv2.split(img_lab)
    
    # More sophisticated reflection detection
    # 1. Overexposure detection with gradient analysis
    bright_mask = v > 235
    
    # 2. Check if bright areas have low gradient (smooth reflections vs textured surfaces)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
    
    # Smooth areas with high brightness are likely reflections
    reflection_mask = bright_mask & (gradient_magnitude < 30) & (s < 30)
    
    # 3. Add specular highlight detection
    specular_mask = (l > 215) & (s < 20) & (gradient_magnitude < 40)
    
    # Combine masks
    final_mask = reflection_mask | specular_mask
    
    # Clean up mask
    kernel = np.ones((3, 3), np.uint8)
    final_mask = cv2.morphologyEx(final_mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    
    # Only process significant reflection areas
    contours, _ = cv2.findContours(final_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered_mask = np.zeros_like(final_mask)
    
    min_area = img.shape[0] * img.shape[1] * 0.0005  # 0.05% of image area
    for contour in contours:
        if cv2.contourArea(contour) > min_area:
            cv2.fillPoly(filtered_mask, [contour], 255)
    
    if np.sum(filtered_mask) > 0:
        # Use adaptive median filtering for reflection areas
        result = img.copy()
        
        # For each reflection region, apply median filtering
        reflection_coords = np.where(filtered_mask > 0)
        if len(reflection_coords[0]) > 0:
            # Create a dilated mask for blending
            dilated_mask = cv2.dilate(filtered_mask, np.ones((7, 7), np.uint8), iterations=1)
            
            # Apply median filter to reduce reflections
            median_filtered = cv2.medianBlur(img, 5)
            
            # Blend original and filtered image
            alpha_blend = dilated_mask.astype(np.float32) / 255.0
            alpha_blend = cv2.GaussianBlur(alpha_blend, (5, 5), 0)
            
            for c in range(3):
                result[:, :, c] = (1 - alpha_blend) * img[:, :, c] + alpha_blend * median_filtered[:, :, c]
        
        return result.astype(np.uint8)
    
    return img

def enhance_contrast_maskrcnn(img):
    """
    Specialized contrast enhancement for Mask R-CNN damage detection
    """
    # Convert to LAB for better control
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Apply CLAHE with parameters optimized for damage detection
    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(6, 6))
    l_enhanced = clahe.apply(l)
    
    # Enhance edges that might indicate damage
    edges = cv2.Canny(l_enhanced, 50, 150)
    edges_dilated = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    
    # Boost contrast in edge areas
    edge_mask = edges_dilated.astype(np.float32) / 255.0
    l_edge_enhanced = l_enhanced + (edge_mask * 20).astype(np.uint8)
    l_edge_enhanced = np.clip(l_edge_enhanced, 0, 255)
    
    # Merge back
    enhanced_lab = cv2.merge((l_edge_enhanced, a, b))
    result = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    
    return result

def process_yolo_detections(results, processed_img, confidence_threshold):
    """
    Process YOLO model detection results
    """
    annotated_img = custom_visualize_yolo(
        processed_img, 
        results, 
        score_threshold=confidence_threshold
    )
    
    detections = []
    damage_counts = {}
    damage_crops = []
    
    if hasattr(results[0].boxes, 'conf'):
        scores = results[0].boxes.conf.cpu().numpy()
        labels = results[0].boxes.cls.cpu().numpy().astype(int)
        boxes = results[0].boxes.xyxy.cpu().numpy()
        
        for i in range(len(scores)):
            confidence = float(scores[i])
            if confidence < confidence_threshold:
                continue
                
            class_id = int(labels[i])
            class_name = CLASS_NAMES[class_id]
            x1, y1, x2, y2 = [float(x) for x in boxes[i]]
            
            if class_name in damage_counts:
                damage_counts[class_name] += 1
            else:
                damage_counts[class_name] = 1
            
            detections.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2]
            })
            
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            pad = 10
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(processed_img.shape[1], x2 + pad)
            y2 = min(processed_img.shape[0], y2 + pad)
            
            crop = processed_img[y1:y2, x1:x2]
            
            _, crop_buffer = cv2.imencode('.jpg', crop)
            crop_str = base64.b64encode(crop_buffer).decode()
            
            damage_crops.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2],
                "crop": crop_str
            })
    
    return annotated_img, detections, damage_counts, damage_crops

def process_dcn_detections(result, processed_img, confidence_threshold):
    """
    Process DCN+ model detection results - updated to handle segmentation masks
    """
    annotated_img = visualize_dcn_detections(
        processed_img, 
        result, 
        score_threshold=confidence_threshold
    )
    
    detections = []
    damage_counts = {}
    damage_crops = []
    
    # Extract detection results from mmdetection format
    pred_instances = result.pred_instances
    
    for i in range(len(pred_instances.bboxes)):
        score = float(pred_instances.scores[i])
        if score < confidence_threshold:
            continue
            
        label = int(pred_instances.labels[i])
        if label >= len(CLASS_NAMES):
            continue
            
        class_name = CLASS_NAMES[label]
        bbox = pred_instances.bboxes[i].cpu().numpy()
        x1, y1, x2, y2 = [float(x) for x in bbox]
        
        if class_name in damage_counts:
            damage_counts[class_name] += 1
        else:
            damage_counts[class_name] = 1
        
        detections.append({
            "class_id": label,
            "class_name": class_name,
            "confidence": score,
            "bbox": [x1, y1, x2, y2]
        })
        
        # Create crop
        x1_int, y1_int, x2_int, y2_int = int(x1), int(y1), int(x2), int(y2)
        
        pad = 10
        x1_int = max(0, x1_int - pad)
        y1_int = max(0, y1_int - pad)
        x2_int = min(processed_img.shape[1], x2_int + pad)
        y2_int = min(processed_img.shape[0], y2_int + pad)
        
        crop = processed_img[y1_int:y2_int, x1_int:x2_int]
        
        _, crop_buffer = cv2.imencode('.jpg', crop)
        crop_str = base64.b64encode(crop_buffer).decode()
        
        damage_crops.append({
            "class_id": label,
            "class_name": class_name,
            "confidence": score,
            "bbox": [x1_int, y1_int, x2_int, y2_int],
            "crop": crop_str
        })
    
    return annotated_img, detections, damage_counts, damage_crops

def visualize_dcn_detections(image, result, score_threshold=0.25, mask_threshold=0.5, alpha=0.5):
    """
    DCN+ visualization - Updated to use segmentation masks like YOLO
    """
    img = image.copy()
    if img.max() <= 1.0:
        img = (img * 255).astype(np.uint8)
    
    orig_h, orig_w = img.shape[:2]
    
    # Extract detection results
    pred_instances = result.pred_instances
    
    for i in range(len(pred_instances.bboxes)):
        score = float(pred_instances.scores[i])
        if score < score_threshold:
            continue
            
        label = int(pred_instances.labels[i])
        if label >= len(CLASS_NAMES):
            continue
            
        color = COLOR_MAPPING.get(label, (255, 255, 255))
        
        # Check if masks are available (for segmentation models)
        if hasattr(pred_instances, 'masks') and pred_instances.masks is not None:
            # Use segmentation masks like original YOLO code
            mask = pred_instances.masks[i].cpu().numpy()
            
            if mask.shape != (orig_h, orig_w):
                mask_resized = cv2.resize(mask.astype(np.uint8), (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
            else:
                mask_resized = mask
            
            binary_mask = mask_resized > mask_threshold
            
            # Apply the same visualization as original YOLO code
            overlay = np.zeros_like(img, dtype=np.uint8)
            overlay[binary_mask] = color
            img = cv2.addWeighted(img, 1.0, overlay, alpha, 0)
            
        else:
            # Fallback to bounding box if no masks available
            bbox = pred_instances.bboxes[i].cpu().numpy()
            x1, y1, x2, y2 = [int(x) for x in bbox]
            
            # Draw bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
            
            # Add label
            damage_name = CLASS_NAMES[label]
            confidence_text = f"{damage_name}: {score:.0%}"
            
            text_size = cv2.getTextSize(confidence_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
            cv2.rectangle(img, (x1, y1 - text_size[1] - 10), (x1 + text_size[0] + 10, y1), color, -1)
            cv2.putText(img, confidence_text, (x1 + 5, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return img

@router.post("/detect")
async def detect_damage(
    file: UploadFile = File(...),
    reduce_reflection: bool = Form(False),
    enhance_contrast: bool = Form(False),
    confidence_threshold: float = Form(0.25),
    model_type: str = Form("yolo")  # New parameter to select model (yolo, dcn, maskrcnn)
):
    """
    Detects and segments car damage in the uploaded image.
    """
    try:
        # Verify the requested model is available
        if model_type == "yolo" and yolo_model is None:
            raise HTTPException(status_code=500, detail="YOLO damage detection model not loaded")
        elif model_type == "dcn" and dcn_model is None:
            # More detailed error message
            if not mmdet_available:
                raise HTTPException(
                    status_code=500, 
                    detail="MMDetection not installed. Please install with: pip install -e C:/Users/mosta/OneDrive/Desktop/VehicleSouq (2)/VehicleSouq/backend/mmdetection"
                )
            else:
                raise HTTPException(
                    status_code=500, 
                    detail="DCN+ model failed to load. Check server logs for detailed error information."
                )
        elif model_type == "maskrcnn" and maskrcnn_model is None:
            raise HTTPException(
                status_code=500, 
                detail="Mask R-CNN model failed to load. Check server logs for detailed error information."
            )
        elif model_type == "mask_rcnn" and maskrcnn_model is None:
            raise HTTPException(status_code=500, detail="Mask R-CNN model not loaded")
        
        contents = await file.read()
        
        pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
        
        np_img = np.array(pil_img)
        
        processed_img = preprocess_image(
            np_img, 
            reduce_reflection=reduce_reflection,
            enhance_contrast=enhance_contrast
        )
        
        _, buffer_orig = cv2.imencode('.jpg', np_img)
        orig_img_str = base64.b64encode(buffer_orig).decode()
        
        _, buffer_processed = cv2.imencode('.jpg', processed_img)
        processed_img_str = base64.b64encode(buffer_processed).decode()
        
        # Use the selected model for detection
        if model_type == "yolo":
            results = yolo_model(processed_img, conf=confidence_threshold)
            annotated_img, detections, damage_counts, damage_crops = process_yolo_detections(
                results, processed_img, confidence_threshold
            )
            model_name = "YOLOv8 Segmentation"
        elif model_type == "dcn":  # DCN+ model
            # Convert image to BGR format for mmdetection
            if processed_img.shape[2] == 3 and processed_img.ndim == 3:
                if processed_img.dtype == np.float32 and processed_img.max() <= 1.0:
                    processed_img = (processed_img * 255).astype(np.uint8)
            
            # Run detection/segmentation
            result = inference_detector(dcn_model, processed_img)
            
            # Process detections directly from mmdetection result
            annotated_img, detections, damage_counts, damage_crops = process_dcn_detections(
                result, processed_img, confidence_threshold
            )
            model_name = "DCN+ Segmentation"
        elif model_type == "maskrcnn":  # Mask R-CNN model
            # Prepare the image for Mask R-CNN with enhanced preprocessing
            device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
            
            # Ensure model is in evaluation mode
            maskrcnn_model.eval()
            
            # Enhanced preprocessing specifically for Mask R-CNN inference
            enhanced_img = preprocess_image_maskrcnn(
                processed_img, 
                reduce_reflection=reduce_reflection,
                enhance_contrast=enhance_contrast
            )
            
            # Convert image to tensor format with better preprocessing
            img_resized = cv2.resize(enhanced_img, (800, 800))
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            
            # Apply normalization that matches training
            img_normalized = img_rgb.astype(np.float32) / 255.0
            
            # Use torchvision functional transforms
            img_tensor = T.functional.to_tensor(img_normalized).unsqueeze(0).to(device)
            
            # Run inference with torch.no_grad() context
            with torch.no_grad():
                maskrcnn_model.eval()  # Double-check evaluation mode
                outputs = maskrcnn_model(img_tensor)
            
            # Handle empty outputs or missing keys
            filtered_outputs = []
            
            if (len(outputs) > 0 and 
                isinstance(outputs[0], dict) and 
                'scores' in outputs[0] and 
                'boxes' in outputs[0] and
                len(outputs[0]['scores']) > 0):
                
                # Filter by confidence and apply NMS
                keep_indices = outputs[0]['scores'] >= max(0.25, confidence_threshold)
                
                if keep_indices.sum() > 0:
                    filtered_output = {}
                    for key in ['boxes', 'scores', 'labels', 'masks']:
                        if key in outputs[0]:
                            filtered_output[key] = outputs[0][key][keep_indices]
                    
                    # Apply additional NMS to remove overlapping detections
                    if 'boxes' in filtered_output and len(filtered_output['boxes']) > 1:
                        try:
                            from torchvision.ops import nms
                            keep_nms = nms(filtered_output['boxes'], filtered_output['scores'], 0.3)
                            for key in filtered_output.keys():
                                filtered_output[key] = filtered_output[key][keep_nms]
                        except Exception as nms_error:
                            logger.warning(f"NMS failed, continuing without NMS: {nms_error}")
                    
                    filtered_outputs = [filtered_output]
                else:
                    # No detections above threshold
                    filtered_outputs = [{}]
            else:
                # No detections at all
                filtered_outputs = [{}]
            
            # Scale the detections back to original size first
            scale_x = processed_img.shape[1] / 800
            scale_y = processed_img.shape[0] / 800
            
            # Scale detection coordinates if we have valid detections
            if (len(filtered_outputs) > 0 and 
                len(filtered_outputs[0]) > 0 and 
                'boxes' in filtered_outputs[0]):
                
                try:
                    # Scale boxes
                    if 'boxes' in filtered_outputs[0] and len(filtered_outputs[0]['boxes']) > 0:
                        filtered_outputs[0]['boxes'][:, [0, 2]] *= scale_x  # x coordinates
                        filtered_outputs[0]['boxes'][:, [1, 3]] *= scale_y  # y coordinates
                    
                    # Resize masks back to original image size
                    if 'masks' in filtered_outputs[0] and len(filtered_outputs[0]['masks']) > 0:
                        original_masks = []
                        for mask in filtered_outputs[0]['masks']:
                            mask_resized = cv2.resize(
                                mask[0].cpu().numpy(), 
                                (processed_img.shape[1], processed_img.shape[0]), 
                                interpolation=cv2.INTER_NEAREST
                            )
                            original_masks.append(torch.tensor(mask_resized).unsqueeze(0))
                        filtered_outputs[0]['masks'] = torch.stack(original_masks)
                except Exception as scale_error:
                    logger.error(f"Error scaling detections: {scale_error}")
                    filtered_outputs = [{}]
            
            # Process detections with ORIGINAL image for natural appearance
            try:
                annotated_img, detections, damage_counts, damage_crops = process_maskrcnn_detections(
                    filtered_outputs, processed_img, max(0.25, confidence_threshold)
                )
            except Exception as process_error:
                logger.error(f"Error processing Mask R-CNN detections: {process_error}")
                # Fallback to original image if processing fails
                annotated_img = processed_img.copy()
                detections = []
                damage_counts = {}
                damage_crops = []
            
            model_name = "Mask R-CNN Segmentation (Enhanced)"
        
        # Encode final annotated image
        _, buffer_full = cv2.imencode('.jpg', annotated_img)
        annotated_img_str = base64.b64encode(buffer_full).decode()
        
        return {
            "status": "success",
            "message": "Car damage detected",
            "model_used": model_name,
            "is_video": False,
            "original_image": orig_img_str,
            "processed_image": processed_img_str,
            "annotated_image": annotated_img_str,
            "detections": detections,
            "damage_counts": damage_counts,
            "damage_crops": damage_crops,
            "preprocessing_applied": {
                "reflection_reduction": reduce_reflection,
                "contrast_enhancement": enhance_contrast
            }
        }
    
    except Exception as e:
        logger.error(f"Error detecting damage: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error detecting damage: {str(e)}")

def process_maskrcnn_detections(outputs, processed_img, confidence_threshold):
    """
    Process Mask R-CNN model detection results with better error handling
    """
    detections = []
    damage_counts = {}
    damage_crops = []
    
    # Handle empty outputs
    if (len(outputs) == 0 or 
        len(outputs[0]) == 0 or 
        'boxes' not in outputs[0] or 
        'scores' not in outputs[0] or
        'labels' not in outputs[0]):
        
        # Return original image if no detections
        return processed_img.copy(), detections, damage_counts, damage_crops
    
    try:
        # Extract predictions and convert numpy types to Python types for JSON serialization
        boxes = outputs[0]['boxes'].cpu().numpy()
        scores = outputs[0]['scores'].cpu().numpy()
        labels = outputs[0]['labels'].cpu().numpy()
        
        # Check if we have masks
        has_masks = 'masks' in outputs[0] and len(outputs[0]['masks']) > 0
        if has_masks:
            masks = outputs[0]['masks'].cpu().numpy()
        
        # Process each detection
        for i in range(len(scores)):
            if scores[i] < confidence_threshold:
                continue
            
            # Get class info (subtract 1 because model outputs 1-indexed labels)
            class_id = int(labels[i]) - 1  # Convert to 0-indexed and ensure it's a Python int
            if class_id < 0 or class_id >= len(CLASS_NAMES):
                continue
                
            class_name = CLASS_NAMES[class_id]
            confidence = float(scores[i])  # Convert to Python float
            x1, y1, x2, y2 = [float(x) for x in boxes[i]]  # Convert to Python floats
            
            # Update damage counts
            if class_name in damage_counts:
                damage_counts[class_name] += 1
            else:
                damage_counts[class_name] = 1
            
            detections.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2]
            })
            
            # Create crop
            x1_int, y1_int, x2_int, y2_int = int(x1), int(y1), int(x2), int(y2)
            
            # Add padding
            pad = 10
            x1_int = max(0, x1_int - pad)
            y1_int = max(0, y1_int - pad)
            x2_int = min(processed_img.shape[1], x2_int + pad)
            y2_int = min(processed_img.shape[0], y2_int + pad)
            
            crop = processed_img[y1_int:y2_int, x1_int:x2_int]
            
            if crop.size > 0:
                _, crop_buffer = cv2.imencode('.jpg', crop)
                crop_str = base64.b64encode(crop_buffer).decode()
                
                damage_crops.append({
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": [x1_int, y1_int, x2_int, y2_int],
                    "crop": crop_str
                })
        
        # Generate annotated image
        annotated_img = visualize_maskrcnn_detections(
            processed_img, 
            outputs, 
            score_threshold=confidence_threshold
        )
        
    except Exception as e:
        logger.error(f"Error in process_maskrcnn_detections: {e}")
        # Return original image on error
        annotated_img = processed_img.copy()
    
    return annotated_img, detections, damage_counts, damage_crops

def custom_visualize_yolo(image, results, score_threshold=0.25, mask_threshold=0.5, alpha=0.6):
    """
    Enhanced visualization for YOLO detections with clearer damage highlighting.
    """
    img = image.copy()
    if img.max() <= 1.0:
        img = (img * 255).astype(np.uint8)
    
    orig_h, orig_w = img.shape[:2]
    
    if hasattr(results[0].boxes, 'conf'):
        scores = results[0].boxes.conf.cpu().numpy()
        labels = results[0].boxes.cls.cpu().numpy().astype(int)
        boxes = results[0].boxes.xyxy.cpu().numpy()
        
        if hasattr(results[0], 'masks') and results[0].masks is not None:
            masks = results[0].masks.data.cpu().numpy()
            if masks.ndim == 4:
                masks = masks[:, 0, :, :]
            
            for i in range(len(scores)):
                if scores[i] < score_threshold:
                    continue
                
                cls = labels[i]
                color = COLOR_MAPPING.get(cls, (255, 255, 255))
                mask = masks[i]
                
                if mask.shape != (orig_h, orig_w):
                    mask_resized = cv2.resize(mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
                else:
                    mask_resized = mask
                
                binary_mask = mask_resized > mask_threshold
                
                # Enhanced highlighting with better visibility
                overlay = img.copy()
                overlay[binary_mask] = color
                
                # Stronger alpha for better visibility
                img = cv2.addWeighted(img, 1.0 - alpha, overlay, alpha, 0)
                class_name = CLASS_NAMES[cls]
                confidence = scores[i]
                
                # Skip highlighting "dent" detections with confidence < 30%
                if class_name == "dent" and confidence < 0.3:
                    continue
                
                # Add clear border outline
                contours, _ = cv2.findContours(binary_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(img, contours, -1, color, 3)
                
                # Add damage label with better contrast
                if len(contours) > 0:
                    # Get the largest contour for label placement
                    largest_contour = max(contours, key=cv2.contourArea)
                    M = cv2.moments(largest_contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        
                        damage_name = CLASS_NAMES[cls]
                        confidence_text = f"{damage_name}: {scores[i]:.0%}"
                        
                        # Enhanced text with background
                        text_size = cv2.getTextSize(confidence_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                        text_x = max(5, cx - text_size[0] // 2)
                        text_y = max(25, cy - 10)
                        
                        # Dark background for text - Fixed the y1 reference error
                        cv2.rectangle(img, 
                                    (text_x - 5, text_y - text_size[1] - 10),
                                    (text_x + text_size[0] + 10, text_y), color, -1)
                        
                        # White text for contrast
                        cv2.putText(img, confidence_text, (text_x, text_y - 2), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        else:
            # Fallback to bounding boxes with enhanced visibility
            for i in range(len(scores)):
                if scores[i] < score_threshold:
                    continue
                
                cls = labels[i]
                color = COLOR_MAPPING.get(cls, (255, 255, 255))
                x1, y1, x2, y2 = boxes[i].astype(int)
                
                # Thicker, more visible bounding box
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 4)
                
                # Enhanced label
                damage_name = CLASS_NAMES[cls]
                confidence_text = f"{damage_name}: {scores[i]:.0%}"
                
                text_size = cv2.getTextSize(confidence_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(img, (x1, y1 - text_size[1] - 10), (x1 + text_size[0] + 10, y1), color, -1)
                cv2.putText(img, confidence_text, (x1 + 5, y1 - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return img

def visualize_maskrcnn_detections(image, outputs, score_threshold=0.25, mask_threshold=0.5, alpha=0.5):
    """
    Enhanced Mask R-CNN visualization with clearer damage highlighting
    """
    img = image.copy()
    if img.max() <= 1.0:
        img = (img * 255).astype(np.uint8)
    
    # Handle empty outputs safely
    if (len(outputs) == 0 or 
        len(outputs[0]) == 0 or 
        'boxes' not in outputs[0] or 
        'scores' not in outputs[0] or
        'labels' not in outputs[0]):
        return img
    
    try:
        boxes = outputs[0]['boxes'].cpu().numpy()
        scores = outputs[0]['scores'].cpu().numpy()
        labels = outputs[0]['labels'].cpu().numpy()
        
        has_masks = 'masks' in outputs[0] and len(outputs[0]['masks']) > 0
        if has_masks:
            masks = outputs[0]['masks'].cpu().numpy()
        
        orig_h, orig_w = img.shape[:2]
        result_img = img.copy()
        
        for i in range(len(scores)):
            if scores[i] < score_threshold:
                continue
            
            class_id = labels[i] - 1
            if class_id < 0 or class_id >= len(CLASS_NAMES):
                continue
                
            color = COLOR_MAPPING.get(class_id, (255, 255, 255))
            
            if has_masks:
                mask = masks[i, 0]
                if mask.shape != (orig_h, orig_w):
                    mask = cv2.resize(mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
                
                binary_mask = mask > mask_threshold
                
                # Enhanced mask processing for better visibility
                kernel = np.ones((3, 3), np.uint8)
                binary_mask = cv2.morphologyEx(binary_mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
                binary_mask = binary_mask.astype(bool)
                
                # Stronger colored overlay for better visibility
                overlay = result_img.copy()
                overlay[binary_mask] = color
                result_img = cv2.addWeighted(result_img, 1.0 - alpha, overlay, alpha, 0)
                
                # Enhanced edge outline with multiple borders
                contours, _ = cv2.findContours(binary_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(result_img, contours, -1, (255, 255, 255), 4)  # White outer border
                cv2.drawContours(result_img, contours, -1, color, 2)  # Colored inner border
                
                # Enhanced text label with better positioning
                mask_coords = np.where(binary_mask)
                if len(mask_coords[0]) > 0:
                    # Find center of mass for better label placement
                    center_y = int(np.mean(mask_coords[0]))
                    center_x = int(np.mean(mask_coords[1]))
                    
                    damage_name = CLASS_NAMES[class_id]
                    label_text = f"{damage_name}: {scores[i]:.0%}"
                    
                    text_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                    text_x = max(10, center_x - text_size[0] // 2)
                    text_y = max(30, center_y - text_size[1] // 2)
                    
                    # Enhanced text background
                    cv2.rectangle(result_img, 
                                 (text_x - 8, text_y - text_size[1] - 8),
                                 (text_x + text_size[0] + 8, text_y + 8),
                                 (0, 0, 0), -1)
                    cv2.rectangle(result_img, 
                                 (text_x - 8, text_y - text_size[1] - 8),
                                 (text_x + text_size[0] + 8, text_y + 8),
                                 color, 2)
                    
                    cv2.putText(result_img, label_text, 
                               (text_x, text_y - 4), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            else:
                # Enhanced bounding box fallback
                x1, y1, x2, y2 = boxes[i].astype(int)
                cv2.rectangle(result_img, (x1, y1), (x2, y2), (255, 255, 255), 4)
                cv2.rectangle(result_img, (x1, y1), (x2, y2), color, 2)
                
                damage_name = CLASS_NAMES[class_id]
                label_text = f"{damage_name}: {scores[i]:.0%}"
                
                text_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(result_img, (x1, y1 - text_size[1] - 15), 
                             (x1 + text_size[0] + 10, y1), (0, 0, 0), -1)
                cv2.rectangle(result_img, (x1, y1 - text_size[1] - 15), 
                             (x1 + text_size[0] + 10, y1), color, 2)
                cv2.putText(result_img, label_text, (x1 + 5, y1 - 8), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    except Exception as e:
        logger.error(f"Error in visualize_maskrcnn_detections: {e}")
        return img
    
    return result_img

@router.post("/detect-from-url")
async def detect_damage_from_url(
    image_url: str = Form(...),
    reduce_reflection: bool = Form(False),
    enhance_contrast: bool = Form(False),
    confidence_threshold: float = Form(0.25),
    model_type: str = Form("yolo")  # Force YOLO model for this endpoint
):
    """
    Detects and segments car damage from an image URL using YOLO model.
    This endpoint fetches the image from the provided URL to avoid CORS issues.
    """
    try:
        logger.info(f"Starting damage detection from URL: {image_url}")
        
        # Verify YOLO model is available
        if yolo_model is None:
            logger.error("YOLO model not loaded")
            raise HTTPException(status_code=500, detail="YOLO damage detection model not loaded")
        
        # Validate image URL
        if not image_url or not image_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Invalid image URL provided")
        
        # Check if this is a local uploads URL and handle it directly
        if "localhost:8000/uploads/" in image_url or "127.0.0.1:8000/uploads/" in image_url:
            logger.info("Detected local uploads URL, accessing file directly")
            
            # Extract filename from URL
            filename = image_url.split('/uploads/')[-1]
            uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
            file_path = os.path.join(uploads_dir, filename)
            
            logger.info(f"Looking for file at: {file_path}")
            
            if not os.path.exists(file_path):
                logger.error(f"File not found at: {file_path}")
                raise HTTPException(status_code=400, detail=f"Image file not found: {filename}")
            
            try:
                # Read the file directly
                with open(file_path, 'rb') as f:
                    image_content = f.read()
                logger.info(f"Successfully read local file. Size: {len(image_content)} bytes")
                
                if len(image_content) == 0:
                    raise HTTPException(status_code=400, detail="Image file is empty")
                    
            except Exception as e:
                logger.error(f"Error reading local file {file_path}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Error reading image file: {str(e)}")
        
        else:
            # Handle external URLs with HTTP requests
            try:
                # Add headers to mimic a browser request
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive',
                }
                
                logger.info(f"Fetching external image from URL: {image_url}")
                response = requests.get(image_url, headers=headers, timeout=30, stream=True, verify=False)
                response.raise_for_status()
                
                # Check if the response is an image
                content_type = response.headers.get('content-type', '').lower()
                logger.info(f"Content type: {content_type}")
                
                if not any(img_type in content_type for img_type in ['image/', 'application/octet-stream']):
                    logger.error(f"Invalid content type: {content_type}")
                    raise HTTPException(status_code=400, detail=f"URL does not point to a valid image. Content-Type: {content_type}")
                
                # Read image content
                image_content = response.content
                logger.info(f"Successfully fetched external image. Size: {len(image_content)} bytes")
                
                if len(image_content) == 0:
                    raise HTTPException(status_code=400, detail="Image content is empty")
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching image from URL {image_url}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Failed to fetch image from URL: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing image URL {image_url}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Error processing image URL: {str(e)}")
        
        # Convert image content to PIL Image
        try:
            pil_img = Image.open(io.BytesIO(image_content)).convert("RGB")
            logger.info(f"Image opened successfully. Size: {pil_img.size}")
        except Exception as e:
            logger.error(f"Error opening image: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")
        
        # Convert to numpy array
        np_img = np.array(pil_img)
        logger.info(f"Image converted to numpy array. Shape: {np_img.shape}")
        
        # Apply preprocessing
        processed_img = preprocess_image(
            np_img, 
            reduce_reflection=reduce_reflection,
            enhance_contrast=enhance_contrast
        )
        
        # Encode original image
        _, buffer_orig = cv2.imencode('.jpg', np_img)
        orig_img_str = base64.b64encode(buffer_orig).decode()
        
        # Encode processed image
        _, buffer_processed = cv2.imencode('.jpg', processed_img)
        processed_img_str = base64.b64encode(buffer_processed).decode()
        
        # Run YOLO detection
        logger.info(f"Running YOLO damage detection with confidence threshold: {confidence_threshold}")
        results = yolo_model(processed_img, conf=confidence_threshold)
        
        # Process YOLO detections
        annotated_img, detections, damage_counts, damage_crops = process_yolo_detections(
            results, processed_img, confidence_threshold
        )
        
        # Encode final annotated image
        _, buffer_full = cv2.imencode('.jpg', annotated_img)
        annotated_img_str = base64.b64encode(buffer_full).decode()
        
        logger.info(f"YOLO detection completed. Found {len(detections)} damage instances")
        logger.info(f"Damage counts: {damage_counts}")
        
        return {
            "status": "success",
            "message": "Car damage detected successfully",
            "model_used": "YOLOv8 Segmentation",
            "source_url": image_url,
            "is_video": False,
            "original_image": orig_img_str,
            "processed_image": processed_img_str,
            "annotated_image": annotated_img_str,
            "detections": detections,
            "damage_counts": damage_counts,
            "damage_crops": damage_crops,
            "preprocessing_applied": {
                "reflection_reduction": reduce_reflection,
                "contrast_enhancement": enhance_contrast
            }
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error detecting damage from URL: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error detecting damage: {str(e)}")
