import ifcopenshell
import ifcopenshell.geom
import numpy as np
from typing import Dict, List, Any, Optional
import logging

# Setup logging
logger = logging.getLogger(__name__)


class IFCGeometryExtractor:
    """Optimized class for extracting geometry from IFC files"""
    
    # Material mappings for different element types
    MATERIAL_COLORS = {
        'IfcWall': '#cccccc', 'IfcSlab': '#e0e0e0', 'IfcColumn': '#888888',
        'IfcBeam': '#996633', 'IfcDoor': '#8B4513', 'IfcWindow': '#87CEEB',
        'IfcStair': '#696969', 'IfcStairFlight': '#556B2F', 'IfcRailing': '#CD853F',
        'IfcRamp': '#808080', 'IfcRoof': '#654321', 'IfcCurtainWall': '#B0C4DE',
        'IfcMember': '#778899', 'IfcPlate': '#A0A0A0', 'IfcCovering': '#F5F5DC',
        'IfcFlowTerminal': '#FF6347', 'IfcBuildingElementProxy': '#DDA0DD',
        'IfcFurnishingElement': '#F0E68C', 'IfcSpace': '#E6E6FA'
    }
    
    # Minimum size threshold (1mm)
    MIN_SIZE_THRESHOLD = 0.001

    def __init__(self, ifc_file_path: str):
        """Initialize geometry extractor with optimized settings"""
        try:
            self.ifc_file = ifcopenshell.open(ifc_file_path)
            self.settings = ifcopenshell.geom.settings()
            self.settings.set(self.settings.USE_WORLD_COORDS, True)
            self.settings.set(self.settings.WELD_VERTICES, True)
            logger.info(f"Initialized geometry extractor for: {ifc_file_path}")
        except Exception as e:
            logger.error(f"Failed to initialize geometry extractor: {e}")
            raise
    
    def extract_simple_geometry(self) -> Dict[str, Any]:
        """Extract simplified geometry for 3D visualization"""
        logger.info("Starting geometry extraction...")
        
        elements = []
        all_products = self.ifc_file.by_type('IfcProduct')
        
        # Filter products with representation upfront
        products_with_geometry = [
            product for product in all_products 
            if hasattr(product, 'Representation') and product.Representation
        ]
        
        logger.info(f"Processing {len(products_with_geometry)} elements with geometry out of {len(all_products)} total")
        
        total_processed = 0
        element_type_counts = {}
        
        for product in products_with_geometry:
            try:
                # Create geometry shape
                shape = ifcopenshell.geom.create_shape(self.settings, product)
                if not shape or not shape.geometry:
                    continue
                
                # Calculate bounding box
                bbox = self._calculate_bounding_box(shape)
                if not self._is_valid_geometry(bbox):
                    continue
                
                # Create element data
                element_data = {
                    'type': product.is_a().lower().replace('ifc', ''),
                    'id': product.GlobalId,
                    'name': getattr(product, 'Name', None) or f'{product.is_a()}_{product.id()}',
                    'boundingBox': bbox,
                    'ifcType': product.is_a()
                }
                
                elements.append(element_data)
                total_processed += 1
                
                # Count element types
                ifc_type = product.is_a()
                element_type_counts[ifc_type] = element_type_counts.get(ifc_type, 0) + 1
                
            except Exception as e:
                logger.debug(f"Error processing {product.is_a()} {product.GlobalId}: {e}")
                continue
        
        logger.info(f"Successfully extracted {total_processed} elements")
        
        # Log element type summary
        if element_type_counts:
            logger.info("Element types extracted:")
            for etype, count in sorted(element_type_counts.items()):
                logger.info(f"  {etype}: {count}")
        
        return {
            'type': 'SimpleIFCModel',
            'elements': elements,
            'totalElements': len(elements),
            'metadata': {
                'totalInFile': len(all_products),
                'withGeometry': len(products_with_geometry),
                'processed': total_processed,
                'elementTypes': element_type_counts,
                'projectName': self._get_project_name()
            }
        }
    
    def _calculate_bounding_box(self, shape) -> Dict[str, List[float]]:
        """Calculate optimized bounding box with coordinate transformation"""
        try:
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            
            if len(verts) == 0:
                return self._default_bbox()
            
            # Transform coordinates: IFC (X,Y,Z) -> Three.js (X,Z,-Y)
            # Swap Y and Z axes for proper Three.js orientation
            transformed_verts = verts.copy()
            transformed_verts[:, [1, 2]] = transformed_verts[:, [2, 1]]
            
            # Calculate bounds
            min_coords = transformed_verts.min(axis=0)
            max_coords = transformed_verts.max(axis=0)
            
            # Ensure minimum size and calculate center
            size = np.maximum(max_coords - min_coords, self.MIN_SIZE_THRESHOLD)
            center = (min_coords + max_coords) / 2
            
            return {
                'min': min_coords.tolist(),
                'max': max_coords.tolist(),
                'center': center.tolist(),
                'size': size.tolist()
            }
            
        except Exception as e:
            logger.warning(f"Error calculating bounding box: {e}")
            return self._default_bbox()
    
    def _is_valid_geometry(self, bbox: Dict[str, List[float]]) -> bool:
        """Check if geometry meets minimum size requirements"""
        size = bbox.get('size', [0, 0, 0])
        return all(s >= self.MIN_SIZE_THRESHOLD for s in size)
    
    def _default_bbox(self) -> Dict[str, List[float]]:
        """Return default bounding box for invalid geometry"""
        default_size = self.MIN_SIZE_THRESHOLD * 10  # 1cm default
        return {
            'min': [0, 0, 0],
            'max': [default_size, default_size, default_size],
            'center': [default_size/2, default_size/2, default_size/2],
            'size': [default_size, default_size, default_size]
        }
    
    def _get_project_name(self) -> str:
        """Extract project name from IFC file"""
        try:
            projects = self.ifc_file.by_type('IfcProject')
            if projects and hasattr(projects[0], 'Name') and projects[0].Name:
                return projects[0].Name
        except Exception as e:
            logger.debug(f"Could not extract project name: {e}")
        return 'IFC Project'
    
    def get_material_color(self, ifc_type: str) -> str:
        """Get material color for element type"""
        return self.MATERIAL_COLORS.get(ifc_type, '#999999')
    
    def extract_geometry_statistics(self) -> Dict[str, Any]:
        """Extract basic statistics about the geometry"""
        try:
            all_products = self.ifc_file.by_type('IfcProduct')
            products_with_geometry = [
                p for p in all_products 
                if hasattr(p, 'Representation') and p.Representation
            ]
            
            # Count by type
            type_counts = {}
            for product in products_with_geometry:
                ptype = product.is_a()
                type_counts[ptype] = type_counts.get(ptype, 0) + 1
            
            return {
                'total_elements': len(all_products),
                'elements_with_geometry': len(products_with_geometry),
                'geometry_percentage': round(len(products_with_geometry) / len(all_products) * 100, 1) if all_products else 0,
                'element_types': type_counts,
                'schema_version': self.ifc_file.schema,
                'project_name': self._get_project_name()
            }
            
        except Exception as e:
            logger.error(f"Error extracting geometry statistics: {e}")
            return {'error': str(e)}


# Utility functions for external use
def extract_ifc_geometry(ifc_file_path: str) -> Dict[str, Any]:
    """Standalone function to extract IFC geometry"""
    try:
        extractor = IFCGeometryExtractor(ifc_file_path)
        return extractor.extract_simple_geometry()
    except Exception as e:
        logger.error(f"Failed to extract geometry from {ifc_file_path}: {e}")
        return {
            'type': 'SimpleIFCModel',
            'elements': [],
            'totalElements': 0,
            'metadata': {'error': str(e)}
        }


def get_ifc_statistics(ifc_file_path: str) -> Dict[str, Any]:
    """Standalone function to get IFC file statistics"""
    try:
        extractor = IFCGeometryExtractor(ifc_file_path)
        return extractor.extract_geometry_statistics()
    except Exception as e:
        logger.error(f"Failed to get statistics from {ifc_file_path}: {e}")
        return {'error': str(e)}