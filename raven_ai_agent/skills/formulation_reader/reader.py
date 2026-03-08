"""
Formulation Reader - Core Data Access Module
============================================

This module provides read-only access to ERPNext doctypes for formulation analysis:
- Item: Product specifications with golden number embedded in item_code
- Batch: Batch management with expiry dates
- Bin: Stock levels per warehouse
- COA AMB: Certificate of Analysis with quality parameters (uses 'specification' field)
- Sales Order: Customer orders with TDS links

Golden Number Format: ITEM_[product(4)][folio(3)][year(2)][plant(1)]
Example: ITEM_0617027231 → product=0617, folio=027, year=23(2023), plant=1

FEFO Key = year * 1000 + folio (lower = older = ship first)

Key Doctypes (from spec):
- Item: item_code (ITEM_XXXXXXXXXX), custom_foxpro_golden_number, custom_product_key
- Batch: name (LOTExxxx), batch_id, item, batch_qty, manufacturing_date, expiry_date
- Bin: item_code, warehouse ('FG to Sell Warehouse - AMB-W'), actual_qty
- COA AMB: name, customer, item_code, lot_number, child table 'COA Quality Test Parameter'
  - Child fields: specification (param name!), result (value), numeric, min_value, max_value, status

All operations are READ-ONLY. No data modifications are allowed.
"""

import frappe
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from decimal import Decimal


# ===========================================
# Data Classes
# ===========================================

@dataclass
class TDSParameter:
    """Technical Data Sheet parameter specification."""
    parameter_code: str
    parameter_name: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    nominal_value: Optional[float] = None
    unit: str = ""
    is_critical: bool = True


@dataclass
class TDSSpec:
    """Complete TDS specification for an item/customer combination."""
    item_code: str
    customer: Optional[str] = None
    sales_order: Optional[str] = None
    parameters: List[TDSParameter] = field(default_factory=list)
    source: str = "item"  # 'item', 'customer_tds', 'sales_order'


@dataclass
class COAParameter:
    """Certificate of Analysis parameter measurement."""
    parameter_code: str
    parameter_name: str
    measured_value: Optional[float] = None
    average: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    result: str = "PENDING"  # PASS, FAIL, PENDING
    samples: List[float] = field(default_factory=list)


@dataclass
class Cunete:
    """Container (cunete/drum) with analytical data."""
    cunete_id: str
    batch_amb_name: str
    container_serial: str
    kilos_available: float
    subproduct: str
    lot: str
    sublot: str
    manufacturing_date: Optional[str] = None
    wwdyy_code: Optional[str] = None
    coa_parameters: List[COAParameter] = field(default_factory=list)


@dataclass
class BatchAMBRecord:
    """Batch AMB record with all related data."""
    name: str
    product: str
    subproduct: str
    lot: str
    sublot: str
    kilos: float
    brix: Optional[float] = None
    total_solids: Optional[float] = None
    manufacturing_date: Optional[str] = None
    wwdyy_code: Optional[str] = None
    warehouse: str = ""
    cunetes: List[Cunete] = field(default_factory=list)
    coa_amb2_name: Optional[str] = None


@dataclass
class BlendInput:
    """Input for blend simulation."""
    cunete_id: str
    mass_kg: float


@dataclass
class BlendParameterResult:
    """Result for a single parameter in blend simulation."""
    parameter_code: str
    parameter_name: str
    predicted_value: float
    tds_min: Optional[float] = None
    tds_max: Optional[float] = None
    result: str = "PENDING"  # PASS, FAIL, N/A
    weighted_inputs: List[Dict] = field(default_factory=list)


@dataclass
class BlendSimulationResult:
    """Complete blend simulation result."""
    target_item: str
    total_mass_kg: float
    parameters: List[BlendParameterResult] = field(default_factory=list)
    cunetes_used: List[Dict] = field(default_factory=list)
    all_pass: bool = False
    summary: str = ""


# ===========================================
# Formulation Reader Class
# ===========================================

# ===========================================
# Golden Number Parsing (from spec section 4.1)
# ===========================================

# Plant code mapping: numeric to name (updated March 2026)
PLANT_CODE_MAP = {
    '1': 'Mix',
    '2': 'Dry',
    '3': 'Juice',
    '4': 'Laboratory',
    '5': 'Formulated'
}

def get_plant_name(plant_code: str) -> str:
    """
    Convert numeric plant code to plant name.
    
    Args:
        plant_code: Single character plant code (1-5)
        
    Returns:
        Plant name (Mix, Dry, Juice, Laboratory, Formulated)
    """
    return PLANT_CODE_MAP.get(plant_code, plant_code)


def parse_golden_number(item_code: str) -> Optional[Dict[str, Any]]:
    """
    Parse golden number components from item code.
    
    Format: ITEM_[product(4)][folio(3)][year(2)][plant(1)]
    Example: ITEM_0617027231
        - Product Code: 0617
        - Folio: 027 (production sequence number)
        - Year: 23 -> 2023
        - Plant: Mix, Dry, Juice, Laboratory, Formulated
    
    Args:
        item_code: Item code string (e.g., 'ITEM_0617027231')
        
    Returns:
        Dict with product, folio, year, full_year, plant, fefo_key, or None if invalid.
    """
    if not item_code or not item_code.startswith('ITEM_'):
        return None
    
    code = item_code[5:]  # Remove 'ITEM_' prefix
    if len(code) != 10:
        return None
    
    try:
        product = code[0:4]      # First 4 chars
        folio = int(code[4:7])   # Next 3 chars
        year = int(code[7:9])    # Next 2 chars
        plant_code = code[9]     # Last char
        
        fefo_key = year * 1000 + folio
        full_year = 2000 + year
        plant_name = get_plant_name(plant_code)
        
        return {
            'product': product,
            'folio': folio,
            'year': year,
            'full_year': full_year,
            'plant': plant_name,
            'fefo_key': fefo_key
        }
    except (ValueError, IndexError):
        return None


# ===========================================
# Standalone Functions (from spec section 4)
# ===========================================

def get_available_batches(
    product_code: Optional[str] = None,
    warehouse: str = 'FG to Sell Warehouse - AMB-W'
) -> List[Dict[str, Any]]:
    """
    Get all batches with available stock, sorted by FEFO.
    
    Queries the Bin doctype for actual stock levels and sorts by FEFO key.
    Lower FEFO key = Older batch = Ship first.
    
    Args:
        product_code: Optional 4-digit product code to filter (e.g., '0612')
        warehouse: Warehouse to query (default: 'FG to Sell Warehouse - AMB-W')
        
    Returns:
        List of batch dicts sorted by FEFO key (oldest first), each containing:
        - item_code, batch_name, warehouse, qty, product, folio, year, fefo_key
    """
    # Build filters for Bin query
    filters = {'actual_qty': ['>', 0]}
    if warehouse:
        filters['warehouse'] = warehouse
    
    # Get bins with stock
    bins = frappe.get_all('Bin',
        filters=filters,
        fields=['item_code', 'warehouse', 'actual_qty']
    )
    
    results = []
    for bin_record in bins:
        parsed = parse_golden_number(bin_record.item_code)
        if not parsed:
            continue
        
        # Filter by product code if specified
        if product_code and parsed['product'] != product_code:
            continue
        
        # Get batch info for this item
        batches = frappe.get_all('Batch',
            filters={'item': bin_record.item_code},
            fields=['name', 'batch_qty', 'expiry_date'],
            limit=1
        )
        
        batch_name = batches[0].name if batches else None
        
        results.append({
            'item_code': bin_record.item_code,
            'batch_name': batch_name,
            'warehouse': bin_record.warehouse,
            'qty': bin_record.actual_qty,
            'product': parsed['product'],
            'folio': parsed['folio'],
            'year': parsed['full_year'],
            'fefo_key': parsed['fefo_key']
        })
    
    # Sort by FEFO key (oldest first)
    results.sort(key=lambda x: x['fefo_key'])
    
    return results


def get_batch_coa_parameters(batch_name: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Get COA quality parameters for a batch.
    
    Supports BOTH COA AMB (external) and COA AMB2 (internal) with fallback logic.
    Uses the 'specification' field as parameter name (per spec).
    
    Priority:
    1. COA AMB (external COA for customers)
    2. COA AMB2 (internal COA from lab results)
    
    Args:
        batch_name: Batch name/lot number (e.g., 'LOTE040')
        
    Returns:
        Dict mapping parameter name to {value, min, max, status, source}, or None if not found.
    """
    # Try COA AMB first (external COA)
    coa_name = None
    coa_source = None
    
    coas = frappe.get_all('COA AMB',
        filters={'lot_number': batch_name},
        fields=['name'],
        limit=1
    )
    
    if coas:
        coa_name = coas[0].name
        coa_source = 'COA AMB'
    else:
        # Fallback to COA AMB2 (internal COA)
        coas2 = frappe.get_all('COA AMB2',
            filters={'lot_number': batch_name},
            fields=['name'],
            limit=1
        )
        
        if coas2:
            coa_name = coas2[0].name
            coa_source = 'COA AMB2'
    
    if not coa_name:
        return None
    
    # Get quality parameters from child table
    # Note: Uses 'specification' field as parameter name (per spec)
    # Different doctypes may have different child table names
    child_table = 'COA Quality Test Parameter' if coa_source == 'COA AMB' else 'COA Quality Test Parameter'
    
    try:
        params = frappe.get_all(child_table,
            filters={
                'parent': coa_name,
                'numeric': 1  # Only numeric parameters for calculations
            },
            fields=['specification', 'result', 'min_value', 'max_value', 'status']
        )
    except Exception:
        # If child table query fails, try alternative approach
        try:
            coa_doc = frappe.get_doc(coa_source, coa_name)
            params = []
            for child_name in ['quality_parameters', 'parameters', 'coa_quality_test_parameter']:
                child_data = coa_doc.get(child_name, [])
                if child_data:
                    params = [p for p in child_data if getattr(p, 'numeric', False) or getattr(p, 'is_numeric', False)]
                    break
        except Exception as e:
            frappe.log_error(f"Error reading COA {coa_name}: {e}", "get_batch_coa_parameters")
            return None
    
    return {
        p.specification: {
            'value': float(p.result) if p.result else None,
            'min': p.min_value,
            'max': p.max_value,
            'status': p.status,
            'source': coa_source
        }
        for p in params if p.specification
    }


def check_tds_compliance(
    batch_params: Dict[str, Dict[str, Any]],
    tds_spec: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check if batch parameters comply with TDS specifications.
    
    Args:
        batch_params: Dict from get_batch_coa_parameters
        tds_spec: Dict mapping parameter name to {min, max}
        
    Returns:
        Dict with:
        - all_pass: bool indicating if all parameters pass
        - parameters: Dict mapping param name to {status, value, min, max}
    """
    results = {}
    all_pass = True
    
    for param_name, spec in tds_spec.items():
        if param_name not in batch_params:
            results[param_name] = {
                'status': 'MISSING',
                'value': None,
                'min': spec.get('min'),
                'max': spec.get('max')
            }
            all_pass = False
            continue
        
        value = batch_params[param_name]['value']
        min_val = spec.get('min')
        max_val = spec.get('max')
        
        if value is None:
            status = 'NO_VALUE'
            all_pass = False
        elif min_val is not None and value < min_val:
            status = 'BELOW_MIN'
            all_pass = False
        elif max_val is not None and value > max_val:
            status = 'ABOVE_MAX'
            all_pass = False
        else:
            status = 'PASS'
        
        results[param_name] = {
            'status': status,
            'value': value,
            'min': min_val,
            'max': max_val
        }
    
    return {'all_pass': all_pass, 'parameters': results}


# ===========================================
# Formulation Reader Class (Extended)
# ===========================================

class FormulationReader:
    """
    Read-only data reader for formulation analysis.
    
    Provides access to:
    - Available batches with FEFO sorting (via Bin doctype)
    - COA AMB parameters (using 'specification' field)
    - TDS specifications
    - Sales Order data
    - Batch AMB records (legacy)
    
    All methods are read-only and do not modify ERPNext data.
    """
    
    # Expose module-level functions as static methods
    parse_golden_number = staticmethod(parse_golden_number)
    get_available_batches = staticmethod(get_available_batches)
    get_batch_coa_parameters = staticmethod(get_batch_coa_parameters)
    check_tds_compliance = staticmethod(check_tds_compliance)
    
    def __init__(self):
        """Initialize the reader."""
        self._cache: Dict[str, Any] = {}
    
    # -------------------------------------------
    # TDS Reading Methods
    # -------------------------------------------
    
    def get_tds_for_sales_order_item(
        self, 
        so_name: str, 
        item_code: str
    ) -> TDSSpec:
        """
        Get TDS specifications for a Sales Order item.
        
        Priority:
        1. Sales Order Item specific TDS link
        2. Customer-specific TDS
        3. Item default TDS specifications
        
        Args:
            so_name: Sales Order name (e.g., "SO-00754")
            item_code: Item code (e.g., "AL-QX-90-10")
            
        Returns:
            TDSSpec with all parameters
        """
        tds_spec = TDSSpec(item_code=item_code, sales_order=so_name)
        
        try:
            # Get Sales Order details
            so = frappe.get_doc("Sales Order", so_name)
            tds_spec.customer = so.customer
            
            # Check for item-specific TDS in Sales Order Item
            for item in so.items:
                if item.item_code == item_code:
                    # Check for TDS link in custom field
                    tds_link = getattr(item, "custom_tds_link", None)
                    if tds_link:
                        tds_spec = self._read_tds_doctype(tds_link, tds_spec)
                        tds_spec.source = "sales_order"
                        return tds_spec
            
            # Try customer-specific TDS
            customer_tds = self._get_customer_tds(so.customer, item_code)
            if customer_tds:
                tds_spec = customer_tds
                tds_spec.source = "customer_tds"
                return tds_spec
            
            # Fall back to item default TDS
            tds_spec = self._get_item_tds(item_code)
            tds_spec.source = "item"
            
        except frappe.DoesNotExistError:
            frappe.log_error(
                f"Sales Order {so_name} not found",
                "FormulationReader.get_tds_for_sales_order_item"
            )
        except Exception as e:
            frappe.log_error(
                f"Error reading TDS: {str(e)}",
                "FormulationReader.get_tds_for_sales_order_item"
            )
        
        return tds_spec
    
    def _get_item_tds(self, item_code: str) -> TDSSpec:
        """Get TDS from Item doctype custom fields."""
        tds_spec = TDSSpec(item_code=item_code, source="item")
        
        try:
            item = frappe.get_doc("Item", item_code)
            
            # Read custom TDS fields
            tds_fields = [
                ("pH", "custom_ph_min", "custom_ph_max", "custom_ph_nominal"),
                ("Polysaccharides", "custom_polysaccharides_min", "custom_polysaccharides_max", "custom_polysaccharides_nominal"),
                ("Ash", "custom_ash_min", "custom_ash_max", "custom_ash_nominal"),
                ("Color", "custom_color_min", "custom_color_max", "custom_color_nominal"),
                ("Total Solids", "custom_total_solids_min", "custom_total_solids_max", "custom_total_solids_nominal"),
            ]
            
            for param_name, min_field, max_field, nominal_field in tds_fields:
                min_val = getattr(item, min_field, None)
                max_val = getattr(item, max_field, None)
                nominal_val = getattr(item, nominal_field, None)
                
                if min_val is not None or max_val is not None:
                    tds_spec.parameters.append(TDSParameter(
                        parameter_code=param_name.lower().replace(" ", "_"),
                        parameter_name=param_name,
                        min_value=float(min_val) if min_val else None,
                        max_value=float(max_val) if max_val else None,
                        nominal_value=float(nominal_val) if nominal_val else None,
                    ))
                    
        except frappe.DoesNotExistError:
            frappe.log_error(
                f"Item {item_code} not found",
                "FormulationReader._get_item_tds"
            )
        
        return tds_spec
    
    def _get_customer_tds(
        self, 
        customer: str, 
        item_code: str
    ) -> Optional[TDSSpec]:
        """Get customer-specific TDS if exists."""
        try:
            # Check for Customer TDS doctype
            tds_records = frappe.get_all(
                "Customer TDS",
                filters={
                    "customer": customer,
                    "item_code": item_code,
                    "docstatus": ["!=", 2]  # Not cancelled
                },
                fields=["name"],
                limit=1
            )
            
            if tds_records:
                return self._read_tds_doctype(tds_records[0].name)
                
        except frappe.DoesNotExistError:
            # Customer TDS doctype may not exist yet
            pass
        
        return None
    
    def _read_tds_doctype(
        self, 
        tds_name: str, 
        tds_spec: Optional[TDSSpec] = None
    ) -> TDSSpec:
        """Read a TDS doctype and extract parameters."""
        if tds_spec is None:
            tds_spec = TDSSpec(item_code="")
        
        try:
            tds_doc = frappe.get_doc("Customer TDS", tds_name)
            tds_spec.item_code = tds_doc.item_code or tds_spec.item_code
            tds_spec.customer = tds_doc.customer
            
            # Read parameter child table
            for param in tds_doc.get("parameters", []):
                tds_spec.parameters.append(TDSParameter(
                    parameter_code=param.parameter_code,
                    parameter_name=param.parameter_name,
                    min_value=param.min_value,
                    max_value=param.max_value,
                    nominal_value=param.nominal_value,
                    unit=param.unit or "",
                    is_critical=param.is_critical or True,
                ))
                
        except Exception as e:
            frappe.log_error(
                f"Error reading TDS {tds_name}: {str(e)}",
                "FormulationReader._read_tds_doctype"
            )
        
        return tds_spec
    
    # -------------------------------------------
    # Batch Reading Methods
    # -------------------------------------------
    
    def get_batches_for_item_and_warehouse(
        self, 
        item_code: str, 
        warehouse: str,
        include_cunetes: bool = True,
        include_coa: bool = False
    ) -> List[BatchAMBRecord]:
        """
        Get all Batch AMB records for an item in a warehouse.
        
        Args:
            item_code: Item code to filter by
            warehouse: Warehouse to filter by
            include_cunetes: Whether to load cunete details
            include_coa: Whether to load COA parameters
            
        Returns:
            List of BatchAMBRecord objects
        """
        batches: List[BatchAMBRecord] = []
        
        try:
            # Query Batch AMB records
            batch_filters = {
                "item": item_code,
                "warehouse": warehouse,
                "docstatus": ["!=", 2],  # Not cancelled
            }
            
            batch_records = frappe.get_all(
                "Batch AMB",
                filters=batch_filters,
                fields=[
                    "name", "product", "subproduct", "lot", "sublot",
                    "kilos", "brix", "total_solids", "manufacturing_date",
                    "wwdyy_code", "warehouse", "coa_amb2"
                ],
                order_by="manufacturing_date asc"
            )
            
            for record in batch_records:
                batch = BatchAMBRecord(
                    name=record.name,
                    product=record.product or "",
                    subproduct=record.subproduct or "",
                    lot=record.lot or "",
                    sublot=record.sublot or "",
                    kilos=float(record.kilos or 0),
                    brix=float(record.brix) if record.brix else None,
                    total_solids=float(record.total_solids) if record.total_solids else None,
                    manufacturing_date=str(record.manufacturing_date) if record.manufacturing_date else None,
                    wwdyy_code=record.wwdyy_code or "",
                    warehouse=record.warehouse or "",
                    coa_amb2_name=record.coa_amb2 or None,
                )
                
                # Load cunete details if requested
                if include_cunetes:
                    batch.cunetes = self._get_cunetes_for_batch(record.name)
                
                # Load COA if requested
                if include_coa and batch.coa_amb2_name:
                    coa_params = self.get_coa_amb2_for_batch(batch.name)
                    for cunete in batch.cunetes:
                        cunete.coa_parameters = coa_params
                
                batches.append(batch)
                
        except frappe.DoesNotExistError:
            # Batch AMB doctype may not exist
            frappe.log_error(
                f"Batch AMB doctype not found",
                "FormulationReader.get_batches_for_item_and_warehouse"
            )
        except Exception as e:
            frappe.log_error(
                f"Error reading batches: {str(e)}",
                "FormulationReader.get_batches_for_item_and_warehouse"
            )
        
        return batches
    
    def _get_cunetes_for_batch(self, batch_amb_name: str) -> List[Cunete]:
        """Get cunete (container) details for a batch."""
        cunetes: List[Cunete] = []
        
        try:
            batch_doc = frappe.get_doc("Batch AMB", batch_amb_name)
            
            # Read from child table (batch_amb_item)
            for item in batch_doc.get("items", []):
                cunete = Cunete(
                    cunete_id=f"{batch_amb_name}-{item.container_serial or item.idx}",
                    batch_amb_name=batch_amb_name,
                    container_serial=item.container_serial or str(item.idx),
                    kilos_available=float(item.kilos or 0),
                    subproduct=item.subproduct or batch_doc.subproduct or "",
                    lot=batch_doc.lot or "",
                    sublot=batch_doc.sublot or "",
                    manufacturing_date=str(batch_doc.manufacturing_date) if batch_doc.manufacturing_date else None,
                    wwdyy_code=batch_doc.wwdyy_code or "",
                )
                cunetes.append(cunete)
                
        except Exception as e:
            frappe.log_error(
                f"Error reading cunetes for {batch_amb_name}: {str(e)}",
                "FormulationReader._get_cunetes_for_batch"
            )
        
        return cunetes
    
    # -------------------------------------------
    # COA Reading Methods
    # -------------------------------------------
    
    def get_coa_amb2_for_batch(self, batch_amb_name: str) -> List[COAParameter]:
        """
        Get COA AMB2 (internal COA) parameters for a batch.
        
        Args:
            batch_amb_name: The Batch AMB document name
            
        Returns:
            List of COAParameter objects
        """
        parameters: List[COAParameter] = []
        
        try:
            # Get the COA AMB2 link from Batch AMB
            batch = frappe.get_doc("Batch AMB", batch_amb_name)
            coa_name = batch.get("coa_amb2") or batch.get("coa_amb")
            
            if not coa_name:
                frappe.log_error(
                    f"No COA linked to batch {batch_amb_name}",
                    "FormulationReader.get_coa_amb2_for_batch"
                )
                return parameters
            
            # Try COA AMB2 first, then COA AMB
            for doctype in ["COA AMB2", "COA AMB"]:
                try:
                    coa_doc = frappe.get_doc(doctype, coa_name)
                    parameters = self._extract_coa_parameters(coa_doc)
                    break
                except frappe.DoesNotExistError:
                    continue
                    
        except frappe.DoesNotExistError:
            frappe.log_error(
                f"Batch {batch_amb_name} not found",
                "FormulationReader.get_coa_amb2_for_batch"
            )
        except Exception as e:
            frappe.log_error(
                f"Error reading COA for batch {batch_amb_name}: {str(e)}",
                "FormulationReader.get_coa_amb2_for_batch"
            )
        
        return parameters
    
    def _extract_coa_parameters(self, coa_doc) -> List[COAParameter]:
        """Extract parameters from a COA document."""
        parameters: List[COAParameter] = []
        
        # Check multiple possible child table names
        param_tables = ["parameters", "quality_parameters", "test_parameters"]
        
        for table_name in param_tables:
            params = coa_doc.get(table_name, [])
            if params:
                for param in params:
                    coa_param = COAParameter(
                        parameter_code=param.parameter_code or "",
                        parameter_name=param.parameter_name or param.parameter_code or "",
                        measured_value=float(param.measured_value) if param.measured_value else None,
                        average=float(param.average) if param.average else None,
                        min_value=float(param.min_value) if param.min_value else None,
                        max_value=float(param.max_value) if param.max_value else None,
                        result=param.result or "PENDING",
                    )
                    parameters.append(coa_param)
                break
        
        return parameters
    
    # -------------------------------------------
    # Blend Simulation Methods
    # -------------------------------------------
    
    def simulate_blend(
        self, 
        blend_inputs: List[BlendInput], 
        target_item: str
    ) -> BlendSimulationResult:
        """
        Simulate a blend by computing weighted averages of parameters.
        
        This is a READ-ONLY calculation that does not create any documents.
        
        Args:
            blend_inputs: List of BlendInput (cunete_id, mass_kg)
            target_item: Target item code for TDS comparison
            
        Returns:
            BlendSimulationResult with predicted parameters and PASS/FAIL status
        """
        result = BlendSimulationResult(
            target_item=target_item,
            total_mass_kg=sum(inp.mass_kg for inp in blend_inputs)
        )
        
        # Get TDS specifications for target item
        tds_spec = self._get_item_tds(target_item)
        
        # Collect cunete data
        cunete_data: Dict[str, Dict] = {}  # cunete_id -> {parameters, mass}
        
        for blend_input in blend_inputs:
            cunete_info = self._get_cunete_info(blend_input.cunete_id)
            if cunete_info:
                cunete_data[blend_input.cunete_id] = {
                    "mass_kg": blend_input.mass_kg,
                    "parameters": cunete_info["parameters"],
                    "batch_amb_name": cunete_info["batch_amb_name"],
                }
                result.cunetes_used.append({
                    "cunete_id": blend_input.cunete_id,
                    "mass_kg": blend_input.mass_kg,
                    "batch_amb_name": cunete_info["batch_amb_name"],
                })
        
        # Compute weighted averages for each parameter
        param_values: Dict[str, List[tuple]] = {}  # param_code -> [(value, mass), ...]
        
        for cunete_id, data in cunete_data.items():
            mass = data["mass_kg"]
            for param in data["parameters"]:
                code = param.parameter_code
                value = param.average or param.measured_value
                if value is not None:
                    if code not in param_values:
                        param_values[code] = []
                    param_values[code].append((value, mass, cunete_id))
        
        # Calculate weighted average for each parameter
        all_pass = True
        
        for param_code, values in param_values.items():
            total_weighted = sum(v * m for v, m, _ in values)
            total_mass = sum(m for _, m, _ in values)
            
            if total_mass > 0:
                predicted_value = total_weighted / total_mass
                
                # Find TDS limits
                tds_param = next(
                    (p for p in tds_spec.parameters if p.parameter_code == param_code),
                    None
                )
                
                tds_min = tds_param.min_value if tds_param else None
                tds_max = tds_param.max_value if tds_param else None
                
                # Determine PASS/FAIL
                param_result = "N/A"
                if tds_min is not None or tds_max is not None:
                    passes_min = tds_min is None or predicted_value >= tds_min
                    passes_max = tds_max is None or predicted_value <= tds_max
                    param_result = "PASS" if (passes_min and passes_max) else "FAIL"
                    
                    if param_result == "FAIL":
                        all_pass = False
                
                # Record weighted inputs for traceability
                weighted_inputs = [
                    {"cunete_id": cid, "value": v, "mass_kg": m, "contribution": (v * m) / total_weighted if total_weighted else 0}
                    for v, m, cid in values
                ]
                
                result.parameters.append(BlendParameterResult(
                    parameter_code=param_code,
                    parameter_name=param_code.replace("_", " ").title(),
                    predicted_value=round(predicted_value, 4),
                    tds_min=tds_min,
                    tds_max=tds_max,
                    result=param_result,
                    weighted_inputs=weighted_inputs,
                ))
        
        result.all_pass = all_pass
        result.summary = self._generate_simulation_summary(result)
        
        return result
    
    def _get_cunete_info(self, cunete_id: str) -> Optional[Dict]:
        """Get cunete information including COA parameters."""
        try:
            # Parse cunete_id to get batch_amb_name
            # Format: BATCH-AMB-NAME-C1 or similar
            parts = cunete_id.rsplit("-", 1)
            if len(parts) >= 1:
                batch_amb_name = parts[0]
                
                # Get COA parameters for this batch
                parameters = self.get_coa_amb2_for_batch(batch_amb_name)
                
                return {
                    "batch_amb_name": batch_amb_name,
                    "parameters": parameters,
                }
        except Exception as e:
            frappe.log_error(
                f"Error getting cunete info for {cunete_id}: {str(e)}",
                "FormulationReader._get_cunete_info"
            )
        
        return None
    
    def _generate_simulation_summary(self, result: BlendSimulationResult) -> str:
        """Generate a human-readable summary of the simulation."""
        lines = [
            f"Blend Simulation for {result.target_item}",
            f"Total Mass: {result.total_mass_kg} kg",
            f"Cunetes Used: {len(result.cunetes_used)}",
            "",
            "Parameter Results:",
        ]
        
        for param in result.parameters:
            status_icon = "✅" if param.result == "PASS" else "❌" if param.result == "FAIL" else "➖"
            range_str = ""
            if param.tds_min is not None and param.tds_max is not None:
                range_str = f" (TDS: {param.tds_min}-{param.tds_max})"
            elif param.tds_min is not None:
                range_str = f" (TDS: ≥{param.tds_min})"
            elif param.tds_max is not None:
                range_str = f" (TDS: ≤{param.tds_max})"
            
            lines.append(f"  {status_icon} {param.parameter_name}: {param.predicted_value}{range_str}")
        
        lines.append("")
        if result.all_pass:
            lines.append("✅ ALL PARAMETERS PASS TDS SPECIFICATIONS")
        else:
            failing = [p.parameter_name for p in result.parameters if p.result == "FAIL"]
            lines.append(f"❌ FAILING PARAMETERS: {', '.join(failing)}")
        
        return "\n".join(lines)


# ===========================================
# Module-level convenience functions
# ===========================================

def get_tds_for_sales_order_item(so_name: str, item_code: str) -> TDSSpec:
    """Get TDS specifications for a Sales Order item."""
    reader = FormulationReader()
    return reader.get_tds_for_sales_order_item(so_name, item_code)


def get_batches_for_item_and_warehouse(
    item_code: str, 
    warehouse: str,
    include_cunetes: bool = True,
    include_coa: bool = False
) -> List[BatchAMBRecord]:
    """Get all Batch AMB records for an item in a warehouse."""
    reader = FormulationReader()
    return reader.get_batches_for_item_and_warehouse(
        item_code, warehouse, include_cunetes, include_coa
    )


def get_coa_amb2_for_batch(batch_amb_name: str) -> List[COAParameter]:
    """Get COA AMB2 parameters for a batch."""
    reader = FormulationReader()
    return reader.get_coa_amb2_for_batch(batch_amb_name)


def simulate_blend(
    blend_inputs: List[Dict], 
    target_item: str
) -> BlendSimulationResult:
    """
    Simulate a blend by computing weighted averages.
    
    Args:
        blend_inputs: List of {"cunete_id": str, "mass_kg": float}
        target_item: Target item code for TDS comparison
        
    Returns:
        BlendSimulationResult
    """
    reader = FormulationReader()
    inputs = [BlendInput(**inp) for inp in blend_inputs]
    return reader.simulate_blend(inputs, target_item)
