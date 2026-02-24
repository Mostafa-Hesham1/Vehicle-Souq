#!/bin/bash
# ==============================================================
# VehicleSouq Backend - Oracle Cloud Startup Script
# Run this once after cloning the repo on the Oracle VM
# ==============================================================

set -e  # Exit on any error

echo "=========================================="
echo "  VehicleSouq Backend Setup"
echo "=========================================="

# 1. Update system & install dependencies
echo "[1/6] Updating system packages..."
sudo apt-get update -y
sudo apt-get install -y python3.10 python3.10-venv python3-pip git curl build-essential

# 2. Create virtual environment
echo "[2/6] Creating Python virtual environment..."
python3.10 -m venv venv
source venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install Python requirements
echo "[3/6] Installing Python requirements..."
pip install -r requirements.txt

# 5. Install mmdetection (special steps required)
echo "[4/6] Installing mmdetection..."
pip install openmim
mim install mmengine
mim install "mmcv>=2.0.0"
cd mmdetection && pip install -e . && cd ..

# 6. Install PM2 to keep the server alive
echo "[5/6] Installing PM2 process manager..."
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2

# 7. Check .env file
echo "[6/6] Checking .env file..."
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found! Creating from example..."
    cp .env.example .env
    echo ">>> Please edit .env with your actual values before starting the server <<<"
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Upload your model files via FileZilla to:"
echo "       ~/Vehicle-Souq/backend/densenet201_best_model.pkl"
echo "       ~/Vehicle-Souq/backend/ML-Models/CarDamageModels/*.pt"
echo "       ~/Vehicle-Souq/backend/ML-Models/CarDamageModels/*.pth"
echo "       ~/Vehicle-Souq/backend/ML-Models/Price-predection/*.pkl"
echo ""
echo "  2. Edit your .env file:"
echo "       nano .env"
echo ""
echo "  3. Start the server with PM2:"
echo "       source venv/bin/activate"
echo "       pm2 start 'uvicorn main:app --host 0.0.0.0 --port 8000' --name vehiclesouq"
echo "       pm2 save"
echo "       pm2 startup"
echo ""
