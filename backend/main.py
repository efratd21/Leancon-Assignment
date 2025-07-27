from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import aiofiles
from typing import Optional
import logging
from ifc_processor import process_ifc_file
from geometry_extractor import IFCGeometryExtractor
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="IFC Processor API",
    description="API for processing IFC files and generating 3D models with quantity tables",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
load_dotenv()
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
ALLOWED_EXTENSIONS = {"ifc"}
MAX_FILE_SIZE = os.getenv("MAX_FILE_SIZE", 100 * 1024 * 1024)  # 100MB

# Create upload directory
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Pydantic models
class APIResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None

class HighlightRequest(BaseModel):
    type: str  # 'element_key' or 'level'
    value: str


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.get("/")
async def root():
    """API information endpoint"""
    return {
        "message": "IFC Processor API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Server health check"""
    return APIResponse(
        success=True,
        message="IFC Processor API is running",
        data={
            "status": "healthy",
            "upload_folder": os.path.abspath(UPLOAD_FOLDER)
        }
    )


@app.post("/upload-ifc")
async def upload_and_process_ifc(file: UploadFile = File(...)):
    """Upload and process IFC file in one endpoint"""
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file selected"
        )
    
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only .ifc files are allowed"
        )
    
    # Read and validate file size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 100MB"
        )
    
    # Save file temporarily
    temp_filepath = os.path.join(UPLOAD_FOLDER, f"temp_{file.filename}")
    
    try:
        async with aiofiles.open(temp_filepath, 'wb') as f:
            await f.write(file_content)
        
        logger.info(f"Processing uploaded file: {file.filename}")
        
        # Process IFC file
        result = process_ifc_file(temp_filepath)
        
        if not result.get('success', False):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get('error', 'Processing failed')
            )
        
        # Extract geometry
        try:
            geom_extractor = IFCGeometryExtractor(temp_filepath)
            geometry_data = geom_extractor.extract_simple_geometry()
            
            # Map element data to geometry
            result['geometry'] = _enhance_geometry_with_element_data(
                geometry_data, result.get('elements', [])
            )
            
            logger.info(f"Successfully processed {len(geometry_data.get('elements', []))} geometry elements")
            
        except Exception as geom_error:
            logger.warning(f"Geometry extraction failed: {geom_error}")
            # Continue without geometry if extraction fails
            result['geometry'] = {'elements': [], 'totalElements': 0}
        
        return APIResponse(
            success=True,
            message=f"File {file.filename} processed successfully",
            data=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing error: {str(e)}"
        )
    finally:
        # Clean up temporary file
        try:
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
        except Exception as e:
            logger.warning(f"Failed to remove temporary file: {e}")


def _enhance_geometry_with_element_data(geometry_data: dict, elements: list) -> dict:
    """Add element_key and level_id to geometry elements"""
    
    # Create mapping from global_id to element data
    element_mapping = {
        element.get('global_id'): {
            'element_key': element.get('element_key'),
            'level_id': element.get('level_id')
        }
        for element in elements
        if element.get('global_id')
    }
    
    # Enhance geometry elements
    for geom_element in geometry_data.get('elements', []):
        geom_id = geom_element.get('id')
        
        if geom_id in element_mapping:
            # Add mapped data
            mapping = element_mapping[geom_id]
            geom_element['element_key'] = mapping['element_key']
            geom_element['level_id'] = mapping['level_id']
        else:
            # Add defaults
            ifc_type = geom_element.get('ifcType', 'Unknown')
            geom_element['element_key'] = f"{ifc_type}_default"
            geom_element['level_id'] = None
    
    logger.info(f"Enhanced {len(geometry_data.get('elements', []))} geometry elements")
    return geometry_data


# Global exception handlers
@app.exception_handler(413)
async def request_entity_too_large_handler(request, exc):
    """Handle files that are too large"""
    return JSONResponse(
        status_code=413,
        content={
            "success": False,
            "error": "File too large. Maximum size is 100MB"
        }
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle non-existent endpoints"""
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "Endpoint not found"
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle internal server errors"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error"
        }
    )