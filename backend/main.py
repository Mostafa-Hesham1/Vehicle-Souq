from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os
import logging
import sys
from datetime import datetime, timedelta
# Import database module to access the db instance
from database import db
# Import ObjectId for working with MongoDB IDs
from bson import ObjectId

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Ensure parent directory is in Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create FastAPI app
app = FastAPI()

# CORS - reads allowed origins from ALLOWED_ORIGINS env var (comma-separated)
# Falls back to localhost for local development
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define uploads directory with absolute path
UPLOADS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads"))
os.makedirs(UPLOADS_DIR, exist_ok=True)
logger.info(f"UPLOADS_DIR set to {UPLOADS_DIR}")

# Import ImageHelper
try:
    from utils.image_helper import ImageHelper
    image_helper = ImageHelper(UPLOADS_DIR)
    # Verify uploads directory is properly set up
    if image_helper.verify_uploads_directory():
        logger.info("Image helper initialized successfully")
    else:
        logger.error("Failed to verify uploads directory")
except Exception as e:
    logger.error(f"Error initializing image helper: {e}")
    image_helper = None

# List all files in the uploads directory for debugging
try:
    files = os.listdir(UPLOADS_DIR)
    logger.info(f"Found {len(files)} files in uploads directory:")
    for file in files:
        try:
            file_path = os.path.join(UPLOADS_DIR, file)
            file_size = os.path.getsize(file_path)
            logger.info(f"  - {file} ({file_size} bytes)")
        except Exception as e:
            logger.error(f"Error accessing file {file}: {e}")
except Exception as e:
    logger.error(f"Error listing files in uploads directory: {e}")

# Setup dependency for image helper
def get_image_helper():
    return image_helper

# Mount the uploads directory for static file access
try:
    app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
    logger.info(f"Successfully mounted /uploads to {UPLOADS_DIR}")
except Exception as e:
    logger.error(f"Failed to mount uploads directory: {e}")

# Direct endpoint to serve image files
@app.get("/image/{image_name}")
async def get_image(image_name: str, image_helper=Depends(get_image_helper)):
    try:
        file_path = image_helper.get_image_path(image_name)
        logger.info(f"Requested image: {image_name}, path: {file_path}")
        if os.path.exists(file_path):
            logger.info(f"Serving image: {file_path}")
            return FileResponse(file_path)
        else:
            logger.warning(f"Image not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"Image not found: {image_name}")
    except Exception as e:
        logger.error(f"Error serving image {image_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check-image/{image_name}")
async def check_image(image_name: str, image_helper=Depends(get_image_helper)):
    exists = image_helper.check_image_exists(image_name)
    return {"exists": exists, "image_name": image_name}

@app.get("/check-files")
async def check_files(image_helper=Depends(get_image_helper)):
    return {"files": image_helper.list_images(), "uploads_dir": UPLOADS_DIR}

# Root endpoint
@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "Server is running properly"}

# Import routers after app definition to avoid circular imports
from routes import auth, car_routes, car_specs, data, damage_detect, predict, price_predict, scrape, train, admin, yolo, messages, debug, profile, damage_reports
from routes.damage_detect import router as damage_detect_router
from routes.damage_reports import router as damage_reports_router

# Mount all routers using the original prefixes to match frontend expectations
app.include_router(scrape.router, prefix="/scrape", tags=["scrape"])
app.include_router(train.router, prefix="/train", tags=["train"])
app.include_router(predict.router, prefix="/predict", tags=["predict"])
app.include_router(yolo.router, prefix="/yolo", tags=["yolo"])
app.include_router(car_specs.router, prefix="/car", tags=["car"])
app.include_router(price_predict.router, prefix="/price", tags=["price"])
app.include_router(data.router, prefix="/data", tags=["data"])
app.include_router(car_routes.router, prefix="/cars", tags=["cars"])
# Add the car_routes router under /api prefix for frontend requests
app.include_router(car_routes.router, prefix="/api/cars", tags=["api-cars"])
app.include_router(damage_detect.router, prefix="/damage", tags=["damage"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])

# Mount auth router twice - once directly and once under /api prefix to support both paths
app.include_router(auth.router)  # For backward compatibility
app.include_router(auth.router, prefix="/api", tags=["auth-api"])  # For frontend API calls

app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(messages.router, prefix="/api", tags=["messages"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])

# Direct auth check endpoint
@app.get("/auth-check")
async def root_auth_check():
    """Direct auth check endpoint"""
    try:
        # Import auth module functions
        from jose import jwt
        import datetime
        # Use hardcoded key for test
        secret_key = "5072851946b935d4a9eae4a277d18f71f77781f3a0164fb41b122190e2ff88ca"
        # Create test payload
        payload = {
            "test": "data",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
        }
        # Create test token
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        # Verify token
        decoded = jwt.decode(token, secret_key, algorithms=["HS256"])
        return {
            "status": "ok",
            "message": "Authentication system is working",
            "test_token": f"{token[:20]}...",
            "decoded": decoded,
            "environment_loaded": os.getenv("JWT_SECRET_KEY") is not None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Authentication error: {str(e)}",
            "error_type": str(type(e))
        }

# Add direct admin endpoints as a fallback if router inclusion doesn't work
@app.get("/admin/stats-direct")
async def admin_stats_direct():
    """Direct access to admin stats"""
    try:
        # Get collection counts directly
        total_users = await db.users.count_documents({})
        total_cars = await db.cars.count_documents({})
        active_listings = await db.listings.count_documents({"status": {"$ne": "sold"}})
        completed_sales = await db.listings.count_documents({"status": "sold"})
        
        return {
            "total_users": total_users,
            "total_cars": total_cars,
            "active_listings": active_listings,
            "completed_sales": completed_sales
        }
    except Exception as e:
        logger.error(f"Error in direct admin stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching admin statistics: {str(e)}"
        )

# Add these new direct endpoints for debugging
@app.get("/admin/users-direct")
async def admin_users_direct():
    """Direct access to admin users (no auth check for debugging)"""
    try:
        cursor = db.users.find({}).sort("created_at", -1)
        
        users = []
        async for user in cursor:
            if "_id" in user:
                user["_id"] = str(user["_id"])
                
            # Remove sensitive information
            if "password" in user:
                del user["password"]
            if "hashed_password" in user:
                del user["hashed_password"]
                
            # Ensure we have created_at
            if "created_at" not in user:
                user["created_at"] = datetime.utcnow()
                
            users.append(user)
        
        if not users:
            # Add sample data for UI testing
            sample_users = [
                {
                    "_id": "admin1",
                    "username": "admin",
                    "email": "admin@vehiclesouq.com",
                    "role": "admin",
                    "created_at": datetime.utcnow() - timedelta(days=60)
                },
                {
                    "_id": "user1",
                    "username": "user1",
                    "email": "user1@example.com",
                    "role": "user",
                    "created_at": datetime.utcnow() - timedelta(days=30)
                }
            ]
            users = sample_users
            
        return {"users": users}
    except Exception as e:
        logger.error(f"Error in direct admin users: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching users: {str(e)}"
        )

@app.get("/admin/listings-direct")
async def admin_listings_direct():
    """Direct access to admin listings (no auth check for debugging)"""
    try:
        cursor = db.listings.find().sort("created_at", -1).limit(10)
        
        listings = []
        async for listing in cursor:
            if "_id" in listing:
                listing["_id"] = str(listing["_id"])
                
            # Process user_id
            if "user_id" in listing and isinstance(listing["user_id"], ObjectId):
                listing["user_id"] = str(listing["user_id"])
                
            # Ensure we have required fields with defaults
            if "price" not in listing:
                listing["price"] = 0
                
            if "created_at" not in listing:
                listing["created_at"] = datetime.utcnow()
                
            listings.append(listing)
        
        if not listings:
            # Add sample data for UI testing
            sample_listings = [
                {
                    "_id": "sample1",
                    "title": "Sample BMW X5",
                    "make": "BMW",
                    "model": "X5",
                    "price": 750000,
                    "created_at": datetime.utcnow(),
                    "user": {"username": "admin"}
                }
            ]
            listings = sample_listings
            
        return {"listings": listings}
    except Exception as e:
        logger.error(f"Error in direct admin listings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching listings: {str(e)}"
        )

@app.get("/admin/growth-metrics-direct") 
async def admin_growth_metrics_direct():
    """Direct access to growth metrics (no auth check for debugging)"""
    try:
        # Calculate time periods
        now = datetime.utcnow()
        
        # Generate sample growth data
        total_users = await db.users.count_documents({})
        total_cars = await db.cars.count_documents({})
        
        return {
            "users_growth": f"+{max(5, int(total_users * 0.1))}",
            "cars_growth": f"+{max(3, int(total_cars * 0.1))}",
            "listings_growth": "+7",
            "sales_growth": "+2"
        }
    except Exception as e:
        logger.error(f"Error in direct growth metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching growth metrics: {str(e)}"
        )

# Add specific handler for admin preflight requests
@app.options("/admin/{rest_of_path:path}")
async def admin_options_handler(rest_of_path: str):
    """Handle OPTIONS requests to /admin routes"""
    logger.info(f"Processing OPTIONS request for /admin/{rest_of_path}")
    return {}

# General CORS preflight handler
@app.options("/{path:path}")
async def cors_preflight(path: str, request: Request):
    """Handle CORS preflight requests for all routes"""
    logger.info(f"CORS preflight request for path: {path}")
    return {"status": "ok"}

@app.get("/cors-debug")
async def cors_debug():
    """Debug endpoint for CORS testing"""
    return {"message": "CORS is working", "timestamp": str(datetime.now())}

# HTTP middleware for logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response

# Exception handler for 404 errors
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    path = request.url.path
    logger.warning(f"404 Not Found: {path}")
    if (path.startswith('/uploads/')):
        image_name = path.split('/')[-1]
        file_path = os.path.join(UPLOADS_DIR, image_name)
        if os.path.exists(file_path):
            logger.info(f"File exists but couldn't be served normally, serving directly: {file_path}")
            return FileResponse(file_path)
    return JSONResponse(
        content={"detail": f"Not Found: {path}"},
        status_code=404,
    )

# Support both /auth/login and /json-login for compatibility
@app.post("/auth/login")
async def auth_login_alias(request: Request):
    # Extract the JSON body from the request
    body = await request.json()
    
    # Call the json_login function from auth.router with the same data
    try:
        # Check for required fields
        if not body.get("email") or not body.get("password"):
            return JSONResponse(
                status_code=422,
                content={"detail": "Email and password are required"}
            )
        
        # Create a UserLogin object to pass to json_login
        from routes.auth import UserLogin
        user_data = UserLogin(email=body["email"], password=body["password"])
        
        # Call the json_login function
        result = await auth.json_login(user_data)
        return result
    except Exception as e:
        logger.error(f"Error in auth/login alias: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Login error: {str(e)}"
        })

# For debugging purposes
@app.get("/debug/routes")
def debug_routes():
    """List all registered routes for debugging purposes"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": route.methods if hasattr(route, "methods") else None
        })
    return {"routes": routes}

# Import auth and security dependencies
from routes.auth import get_current_user

# Modified version of the marketplace endpoint to handle all car listings requests
@app.get("/api/cars/listings")
async def get_all_listings(
    page: int = 1, 
    limit: int = 24, 
    minYear: int = 2000,
    maxYear: int = 2025,
    sortBy: str = "newest",
    exclude_current_user: bool = True,
    current_user = Depends(get_current_user)
):
    """Get all car listings with option to exclude the current user's listings"""
    try:
        # Get user ID from current user
        user_id = None
        if current_user and "_id" in current_user:
            user_id = str(current_user["_id"])
            logger.info(f"Current user ID: {user_id}")
        else:
            logger.warning("No user ID found in current_user")
        
        # Skip and limit for pagination
        skip = (page - 1) * limit
        
        # Build filter query
        filter_query = {
            "year": {"$gte": minYear, "$lte": maxYear}
        }
        
        # Add user filtering - exclude current user's listings
        if exclude_current_user and user_id:
            filter_query["user_id"] = {"$ne": ObjectId(user_id)}
            logger.info(f"Excluding listings from user_id: {user_id}")
            logger.info(f"Final filter query: {filter_query}")
        
        # Log the number of user's own listings for debugging
        if user_id:
            own_listings_count = await db.listings.count_documents({"user_id": ObjectId(user_id)})
            logger.info(f"User {user_id} has {own_listings_count} listings")
        
        # Determine sort order
        if sortBy == "newest":
            sort_field = "created_at"
            sort_order = -1  # Descending
        elif sortBy == "oldest":
            sort_field = "created_at"
            sort_order = 1   # Ascending
        elif sortBy == "price_low":
            sort_field = "price"
            sort_order = 1   # Ascending
        elif sortBy == "price_high":
            sort_field = "price"
            sort_order = -1  # Descending
        else:
            sort_field = "created_at"
            sort_order = -1  # Default to newest
            
        # Get total count of matching listings
        total_listings = await db.listings.count_documents(filter_query)
        logger.info(f"Found {total_listings} listings matching filter")
        
        # Get paginated listings
        cursor = db.listings.find(filter_query).sort(sort_field, sort_order).skip(skip).limit(limit)
        
        listings = []
        user_listings_found = 0
        
        async for listing in cursor:
            if "_id" in listing:
                listing["_id"] = str(listing["_id"])
            
            # Convert ObjectId to string for user_id
            listing_user_id = None
            if "user_id" in listing:
                if isinstance(listing["user_id"], ObjectId):
                    listing_user_id = str(listing["user_id"])
                    listing["user_id"] = listing_user_id
                else:
                    listing_user_id = listing["user_id"]
            
            # Count listings from current user for debugging
            if listing_user_id == user_id:
                user_listings_found += 1
                logger.warning(f"Found user's own listing in results: {listing['_id']}")
                
                # Skip this listing if we're supposed to exclude current user's listings
                if exclude_current_user:
                    logger.warning(f"Filtering failed for listing {listing['_id']} - manually skipping")
                    continue
                
            listings.append(listing)
        
        if user_listings_found > 0:
            logger.warning(f"Found {user_listings_found} of the user's own listings in results despite filtering")
        
        # Calculate total pages
        total_pages = (total_listings + limit - 1) // limit if total_listings > 0 else 1
        
        return {
            "listings": listings,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_listings": total_listings,
                "has_next": page < total_pages,
                "has_prev": page > 1
            },
            "debug": {
                "user_id": user_id,
                "filter_query": str(filter_query),
                "exclude_current_user": exclude_current_user,
                "user_listings_found": user_listings_found
            }
        }
        
    except Exception as e:
        logger.error(f"Error in listings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching listings: {str(e)}"
        )

# Keep the marketplace endpoint but have it call the listings endpoint with exclude_current_user=True
@app.get("/api/cars/marketplace")
async def get_marketplace_listings(
    page: int = 1, 
    limit: int = 24, 
    minYear: int = 2000,
    maxYear: int = 2025,
    sortBy: str = "newest",
    current_user = Depends(get_current_user)
):
    """Get all car listings except those belonging to the current user"""
    return await get_all_listings(
        page=page,
        limit=limit,
        minYear=minYear,
        maxYear=maxYear,
        sortBy=sortBy,
        exclude_current_user=True,
        current_user=current_user
    )

# Add an endpoint specifically for user's own listings
@app.get("/api/cars/my-listings")
async def get_user_listings(
    page: int = 1, 
    limit: int = 24,
    current_user = Depends(get_current_user)
):
    """Get only the current user's listings"""
    try:
        # Get user ID from current user
        user_id = str(current_user["_id"]) if "_id" in current_user else None
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Skip and limit for pagination
        skip = (page - 1) * limit
        
        # Build filter query
        filter_query = {
            "user_id": ObjectId(user_id)
        }
        
        # Get total count of matching listings
        total_listings = await db.listings.count_documents(filter_query)
        
        # Get paginated listings
        cursor = db.listings.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
        
        listings = []
        async for listing in cursor:
            if "_id" in listing:
                listing["_id"] = str(listing["_id"])
            
            # Convert ObjectId to string for user_id
            if "user_id" in listing and isinstance(listing["user_id"], ObjectId):
                listing["user_id"] = str(listing["user_id"])
                
            listings.append(listing)
            
        # Calculate total pages
        total_pages = (total_listings + limit - 1) // limit if total_listings > 0 else 1
        
        return {
            "listings": listings,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_listings": total_listings,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
        
    except Exception as e:
        logger.error(f"Error in user listings: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching user listings: {str(e)}"
        )

# Enhanced endpoint for fetching a single car by ID
@app.get("/api/cars/{car_id}")
async def get_car_by_id(car_id: str, request: Request):
    """Get details for a specific car by ID"""
    logger.info(f"Car details requested for ID: {car_id} from URL: {request.url}")
    try:
        # Validate the ID format
        if not ObjectId.is_valid(car_id):
            logger.warning(f"Invalid ObjectId format: {car_id}")
            raise HTTPException(status_code=400, detail="Invalid car ID format")
        
        # Find the car in listings collection
        car = await db.listings.find_one({"_id": ObjectId(car_id)})
        
        if not car:
            logger.warning(f"Car not found with ID: {car_id}")
            raise HTTPException(status_code=404, detail=f"Car with ID {car_id} not found")
        
        # Convert ObjectId to string for all fields
        if "_id" in car:
            car["_id"] = str(car["_id"])
        
        if "user_id" in car and isinstance(car["user_id"], ObjectId):
            car["user_id"] = str(car["user_id"])
        
        # Try to get user details if available
        if "user_id" in car:
            user = await db.users.find_one({"_id": ObjectId(car["user_id"])})
            if user:
                car["seller"] = {
                    "username": user.get("username", "Unknown"),
                    "email": user.get("email"),
                    "phone": user.get("phone", "No phone provided")
                }
        
        logger.info(f"Returning car details for ID: {car_id}")
        return car
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching car by ID {car_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving car details: {str(e)}"
        )

# Alternative endpoint for car details - in case frontend uses a different pattern
@app.get("/api/cars/details/{car_id}")
async def get_car_details(car_id: str, request: Request):
    """Alternative endpoint for car details"""
    logger.info(f"Car details accessed through alternative endpoint: {car_id}")
    return await get_car_by_id(car_id, request)

# Another alternative endpoint for my-listings
@app.get("/cars/my-listings/{car_id}")
@app.get("/api/cars/my-listings/{car_id}")
async def get_my_car_details(car_id: str, request: Request):
    """Alternative endpoint for user's own car details"""
    logger.info(f"My car details accessed: {car_id}")
    return await get_car_by_id(car_id, request)

# Provide car details through original /cars endpoint as well
@app.get("/cars/{car_id}")
async def get_original_car_details(car_id: str, request: Request):
    """Original endpoint pattern for car details"""
    logger.info(f"Car details accessed through original endpoint: {car_id}")
    return await get_car_by_id(car_id, request)

# Debug endpoint to check what URLs are available
@app.get("/api/debug/car-detail-urls/{car_id}")
async def debug_car_urls(car_id: str):
    """Debug endpoint to check all available URLs for a car ID"""
    base_url = "http://localhost:8000"
    urls = [
        f"{base_url}/api/cars/{car_id}",
        f"{base_url}/api/cars/details/{car_id}",
        f"{base_url}/cars/my-listings/{car_id}",
        f"{base_url}/api/cars/my-listings/{car_id}",
        f"{base_url}/cars/{car_id}"
    ]
    return {"car_id": car_id, "available_urls": urls}

@app.get("/api/cars/listing/{listing_id}")
async def get_api_listing_by_id(listing_id: str):
    """API endpoint to get car listing details"""
    logger.info(f"API car listing details requested for ID: {listing_id}")
    try:
        # Redirect to the car_routes router's endpoint
        return await car_routes.get_listing_details(listing_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in API listing endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving car listing details: {str(e)}"
        )

# Include routers - Make sure car_routes is included with the correct prefix
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(car_routes.router, prefix="/car", tags=["cars"])
app.include_router(profile.router, prefix="/profile", tags=["profile"])
app.include_router(damage_detect_router, prefix="/damage", tags=["damage_detection"])
app.include_router(damage_reports_router, prefix="/damage", tags=["damage_reports"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)