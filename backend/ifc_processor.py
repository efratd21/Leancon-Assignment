import ifcopenshell
import ifcopenshell.util.element as element_util
import ifcopenshell.util.placement as placement_util
from collections import defaultdict
import logging

# Setup logging
logger = logging.getLogger(__name__)


class IFCProcessor:
    """Optimized IFC file processor for extracting building elements and quantities"""
    
    # Define relevant element types upfront
    RELEVANT_ELEMENT_TYPES = {
        'IfcWall', 'IfcSlab', 'IfcColumn', 'IfcBeam', 'IfcDoor', 'IfcWindow',
        'IfcStair', 'IfcStairFlight', 'IfcRailing', 'IfcRamp', 'IfcRoof',
        'IfcCurtainWall', 'IfcMember', 'IfcPlate', 'IfcCovering',
        'IfcFlowTerminal', 'IfcBuildingElementProxy', 'IfcFurnishingElement', 'IfcSpace'
    }
    
    # Unit mappings for different element types
    UNIT_MAPPINGS = {
        'IfcWall': 'm²', 'IfcSlab': 'm²', 'IfcColumn': 'units', 'IfcBeam': 'm',
        'IfcDoor': 'units', 'IfcWindow': 'units', 'IfcStair': 'units',
        'IfcStairFlight': 'units', 'IfcRailing': 'm', 'IfcRamp': 'm²',
        'IfcRoof': 'm²', 'IfcCurtainWall': 'm²', 'IfcMember': 'm',
        'IfcPlate': 'm²', 'IfcCovering': 'm²', 'IfcFlowTerminal': 'units',
        'IfcBuildingElementProxy': 'units', 'IfcFurnishingElement': 'units',
        'IfcSpace': 'm³'
    }

    def __init__(self, ifc_path):
        """Initialize IFC file processor"""
        try:
            self.ifc_file = ifcopenshell.open(ifc_path)
            self.levels_data = {}
            self.quantity_table = defaultdict(lambda: defaultdict(int))
            logger.info(f"Successfully opened IFC file: {ifc_path}")
        except Exception as e:
            logger.error(f"Failed to open IFC file {ifc_path}: {e}")
            raise
        
    def get_building_levels(self):
        """Extract and sort building levels by elevation"""
        levels = []
        building_storeys = self.ifc_file.by_type('IfcBuildingStorey')
        
        for storey in building_storeys:
            elevation = self._get_level_elevation(storey)
            level_data = {
                'id': storey.id(),
                'name': storey.Name or f'Level {storey.id()}',
                'elevation': elevation,
                'global_id': storey.GlobalId
            }
            levels.append(level_data)
        
        # Sort by elevation and cache
        levels.sort(key=lambda x: x['elevation'])
        self.levels_data = {level['id']: level for level in levels}
        
        logger.info(f"Found {len(levels)} building levels")
        return levels
    
    def _get_level_elevation(self, storey):
        """Get level elevation with error handling"""
        try:
            placement = storey.ObjectPlacement
            if placement:
                matrix = placement_util.get_local_placement(placement)
                if matrix is not None:
                    return matrix[2][3]  # Z coordinate
        except Exception as e:
            logger.warning(f"Could not get elevation for storey {storey.GlobalId}: {e}")
        return 0.0
    
    def process_elements(self):
        """Process all relevant elements with geometry"""
        logger.info("Starting element processing...")
        
        # Get all products at once
        all_products = self.ifc_file.by_type('IfcProduct')
        
        # Filter elements with geometry and relevant types
        relevant_elements = [
            product for product in all_products
            if (hasattr(product, 'Representation') and 
                product.Representation and
                product.is_a() in self.RELEVANT_ELEMENT_TYPES)
        ]
        
        logger.info(f"Processing {len(relevant_elements)} relevant elements out of {len(all_products)} total")
        
        processed_elements = []
        for element in relevant_elements:
            try:
                element_data = self._process_single_element(element)
                if element_data:
                    processed_elements.append(element_data)
            except Exception as e:
                logger.warning(f"Error processing element {element.GlobalId}: {e}")
                continue
        
        logger.info(f"Successfully processed {len(processed_elements)} elements")
        return processed_elements
    
    def _process_single_element(self, element):
        """Process individual element efficiently"""
        # Get basic properties
        element_info = {
            'id': element.id(),
            'global_id': element.GlobalId,
            'type': element.is_a(),
            'name': getattr(element, 'Name', None) or f'{element.is_a()}_{element.id()}',
            'level_id': self._get_element_level(element)
        }
        
        # Get dimensions and quantities
        dimensions = self._get_element_dimensions(element)
        element_info['dimensions'] = dimensions
        element_info['quantities'] = {'Count': 1.0}  # Simplified quantity
        
        # Create element key and update quantity table
        element_key = self._create_element_key(element_info['type'], dimensions)
        element_info['element_key'] = element_key
        
        self._update_quantity_table(element_key, element_info['level_id'])
        
        return element_info
    
    def _get_element_level(self, element):
        """Determine element level efficiently"""
        # First try: direct container
        try:
            container = element_util.get_container(element)
            if container and container.is_a('IfcBuildingStorey'):
                return container.id()
        except:
            pass
        
        # Second try: geometric placement
        try:
            placement = getattr(element, 'ObjectPlacement', None)
            if placement:
                matrix = placement_util.get_local_placement(placement)
                if matrix is not None:
                    z_coordinate = matrix[2][3]
                    return self._find_closest_level(z_coordinate)
        except:
            pass
        
        return None
    
    def _find_closest_level(self, z_coordinate):
        """Find closest level by Z coordinate"""
        if not self.levels_data:
            return None
            
        closest_level = min(
            self.levels_data.values(),
            key=lambda level: abs(z_coordinate - level['elevation'])
        )
        return closest_level['id']
    
    def _get_element_dimensions(self, element):
        """Extract element dimensions from property sets"""
        dimensions = {}
        
        try:
            psets = element_util.get_psets(element)
            dimension_props = {'Length', 'Width', 'Height', 'Thickness', 'Area', 'Volume', 'Depth'}
            
            for pset_data in psets.values():
                for prop_name, prop_value in pset_data.items():
                    if (prop_name in dimension_props and 
                        isinstance(prop_value, (int, float)) and 
                        prop_value > 0):
                        dimensions[prop_name] = round(prop_value, 2)
        except Exception as e:
            logger.debug(f"Could not extract dimensions for {element.GlobalId}: {e}")
        
        return dimensions
    
    def _create_element_key(self, element_type, dimensions):
        """Create consistent element key"""
        if not dimensions:
            return f"{element_type}_default"
        
        # Sort dimensions for consistency
        dim_parts = [
            f"{key}:{value}" 
            for key, value in sorted(dimensions.items())
            if value > 0
        ]
        
        return f"{element_type}_{'-'.join(dim_parts)}" if dim_parts else f"{element_type}_default"
    
    def _update_quantity_table(self, element_key, level_id):
        """Update quantity table efficiently"""
        self.quantity_table[element_key]['total_count'] += 1
        
        if level_id:
            level_key = f'level_{level_id}_count'
            self.quantity_table[element_key][level_key] += 1
    
    def generate_quantity_table_data(self):
        """Generate final quantity table data"""
        if not self.quantity_table:
            logger.warning("No quantity data available")
            return {'table_data': [], 'levels': list(self.levels_data.values())}
        
        table_data = []
        
        for element_key, quantities in self.quantity_table.items():
            element_type = element_key.split('_')[0]
            
            # Calculate level quantities
            level_quantities = {}
            total_count = quantities.get('total_count', 0)
            
            for qty_name, qty_value in quantities.items():
                if qty_name.startswith('level_') and qty_name.endswith('_count'):
                    level_id = int(qty_name.split('_')[1])
                    level_quantities[level_id] = qty_value
            
            row = {
                'element_key': element_key,
                'element_type': element_type,
                'unit_of_measure': self.UNIT_MAPPINGS.get(element_type, 'units'),
                'total_quantity': total_count,
                'level_quantities': level_quantities
            }
            table_data.append(row)
        
        # Sort by element type for consistency
        table_data.sort(key=lambda x: x['element_type'])
        
        levels = sorted(self.levels_data.values(), key=lambda x: x['elevation'])
        
        logger.info(f"Generated quantity table with {len(table_data)} element types")
        return {
            'table_data': table_data,
            'levels': levels
        }
    
    def get_project_info(self):
        """Get basic project information"""
        try:
            projects = self.ifc_file.by_type('IfcProject')
            if projects:
                project = projects[0]
                return {
                    'name': project.Name or 'Unnamed Project',
                    'description': getattr(project, 'Description', None),
                    'schema': self.ifc_file.schema
                }
        except Exception as e:
            logger.warning(f"Could not extract project info: {e}")
        
        return {
            'name': 'IFC Project',
            'description': None,
            'schema': getattr(self.ifc_file, 'schema', 'Unknown')
        }


def process_ifc_file(ifc_path):
    """Main function for processing IFC file - optimized version"""
    logger.info(f"Starting IFC file processing: {ifc_path}")
    
    try:
        processor = IFCProcessor(ifc_path)
        
        # Process in order
        levels = processor.get_building_levels()
        elements = processor.process_elements()
        quantity_data = processor.generate_quantity_table_data()
        project_info = processor.get_project_info()
        
        # Create geometry export data
        geometry_data = {
            'file_path': ifc_path,
            'elements_count': len(elements),
            'levels': levels,
            'project_info': project_info
        }
        
        logger.info(f"Processing complete: {len(levels)} levels, {len(elements)} elements")
        
        return {
            'success': True,
            'levels': levels,
            'elements': elements,
            'quantity_table': quantity_data,
            'geometry': geometry_data,
            'project_info': project_info
        }
        
    except Exception as e:
        logger.error(f"Error processing IFC file: {e}")
        return {
            'success': False,
            'error': str(e)
        }