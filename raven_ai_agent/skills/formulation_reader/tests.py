"""
Tests for Formulation Reader Skill - Phase 1
============================================

Test cases aligned with PHASE1_FORMULATION_READER_AGENT.md specification:

Section 8 - TEST CASES:
- Test 1: Parse Golden Number - parse_golden_number('ITEM_0617027231')
- Test 2: FEFO Sorting - verify oldest batch first
- Test 3: Stock Query - get_available_batches('0616')

Additional tests:
- TC1.3: Simulate blend with cunetes - verify weighted average calculation
- TC1.4: Check TDS compliance - verify PASS/FAIL flags
- TC1.5: check_tds_compliance function - verify all statuses
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal


# ===========================================
# Test 1: Parse Golden Number (from spec section 8)
# ===========================================

class TestParseGoldenNumber(unittest.TestCase):
    """
    Test golden number parsing as per spec section 4.1 and 8.
    
    Expected for ITEM_0617027231:
    {product: '0617', folio: 27, year: 23, full_year: 2023, plant: '1', fefo_key: 23027}
    """
    
    def setUp(self):
        """Set up test fixtures with mocked frappe."""
        self.frappe_mock = MagicMock()
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': self.frappe_mock})
        self.frappe_patcher.start()
        
        from raven_ai_agent.skills.formulation_reader.reader import parse_golden_number
        self.parse_golden_number = parse_golden_number
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_parse_valid_golden_number(self):
        """Test 1 from spec: Parse ITEM_0617027231."""
        result = self.parse_golden_number('ITEM_0617027231')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['product'], '0617')
        self.assertEqual(result['folio'], 27)
        self.assertEqual(result['year'], 23)
        self.assertEqual(result['full_year'], 2023)
        self.assertEqual(result['plant'], '1')
        self.assertEqual(result['fefo_key'], 23027)
    
    def test_parse_different_plants(self):
        """Test parsing items from different plants."""
        # Mix, Dry, Juice, Laboratory, Formulated
        test_cases = [
            ('ITEM_0617027231', 'Mix'),  # Mix
            ('ITEM_0617027232', 'Dry'),  # Dry
            ('ITEM_0617027233', 'Juice'),  # Juice
            ('ITEM_0617027234', 'Laboratory'),  # Lab
            ('ITEM_0617027235', 'Formulated'),  # Formulated
        ]
        
        for item_code, expected_plant in test_cases:
            result = self.parse_golden_number(item_code)
            self.assertEqual(result['plant'], expected_plant, f"Failed for {item_code}")
    
    def test_parse_fefo_key_calculation(self):
        """Verify FEFO key = year * 1000 + folio."""
        test_cases = [
            ('ITEM_0617027231', 23027),  # 23*1000 + 27 = 23027
            ('ITEM_0637031241', 24031),  # 24*1000 + 31 = 24031
            ('ITEM_0612200241', 24200),  # 24*1000 + 200 = 24200
            ('ITEM_0615050251', 25050),  # 25*1000 + 50 = 25050
        ]
        
        for item_code, expected_fefo in test_cases:
            result = self.parse_golden_number(item_code)
            self.assertEqual(result['fefo_key'], expected_fefo, f"Failed for {item_code}")
    
    def test_parse_invalid_prefix(self):
        """Items without ITEM_ prefix should return None."""
        invalid_codes = [
            '0617027231',           # No prefix
            'PROD_0617027231',      # Wrong prefix
            'ITM_0617027231',       # Partial prefix
            None,                   # None value
            '',                     # Empty string
        ]
        
        for code in invalid_codes:
            result = self.parse_golden_number(code)
            self.assertIsNone(result, f"Should return None for: {code}")
    
    def test_parse_invalid_length(self):
        """Item codes with wrong length should return None."""
        invalid_codes = [
            'ITEM_061702723',      # 9 chars after prefix
            'ITEM_06170272311',    # 11 chars after prefix
            'ITEM_',              # Just prefix
        ]
        
        for code in invalid_codes:
            result = self.parse_golden_number(code)
            self.assertIsNone(result, f"Should return None for: {code}")


# ===========================================
# Test 2: FEFO Sorting (from spec section 8)
# ===========================================

class TestFEFOSorting(unittest.TestCase):
    """
    Test 2 from spec: FEFO Sorting.
    
    Input: ['ITEM_0612200241', 'ITEM_0617027231', 'ITEM_0615050251']
    Expected Order: ITEM_0617027231 (23027), ITEM_0612200241 (24200), ITEM_0615050251 (25050)
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.frappe_mock = MagicMock()
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': self.frappe_mock})
        self.frappe_patcher.start()
        
        from raven_ai_agent.skills.formulation_reader.reader import parse_golden_number
        self.parse_golden_number = parse_golden_number
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_fefo_sorting_order(self):
        """Verify FEFO sorting produces oldest first order."""
        item_codes = ['ITEM_0612200241', 'ITEM_0617027231', 'ITEM_0615050251']
        
        # Parse and sort by FEFO key
        parsed = [self.parse_golden_number(code) for code in item_codes]
        parsed_with_codes = list(zip(item_codes, parsed))
        sorted_items = sorted(parsed_with_codes, key=lambda x: x[1]['fefo_key'])
        
        expected_order = [
            'ITEM_0617027231',  # FEFO 23027 (oldest)
            'ITEM_0612200241',  # FEFO 24200
            'ITEM_0615050251',  # FEFO 25050 (newest)
        ]
        
        actual_order = [item[0] for item in sorted_items]
        self.assertEqual(actual_order, expected_order)
    
    def test_fefo_key_comparison(self):
        """Verify FEFO key comparisons are correct."""
        # Lower FEFO key = Older batch = Ship first
        old_batch = self.parse_golden_number('ITEM_0617027231')  # 23027
        new_batch = self.parse_golden_number('ITEM_0637031241')  # 24031
        
        self.assertLess(old_batch['fefo_key'], new_batch['fefo_key'])


# ===========================================
# Test 3: Stock Query (from spec section 8)
# ===========================================

class TestGetAvailableBatches(unittest.TestCase):
    """
    Test 3 from spec: get_available_batches('0616').
    
    Expected: List of batches for product 0616, sorted by FEFO.
    """
    
    def setUp(self):
        """Set up test fixtures with mocked frappe."""
        self.frappe_mock = MagicMock()
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': self.frappe_mock})
        self.frappe_patcher.start()
        
        # Import after patching
        import raven_ai_agent.skills.formulation_reader.reader as reader_module
        self.reader_module = reader_module
        
        # Set up the frappe mock on the module
        reader_module.frappe = self.frappe_mock
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_get_available_batches_filters_by_product(self):
        """Test that batches are filtered by product code."""
        # Mock Bin data with multiple products
        mock_bins = [
            MagicMock(item_code='ITEM_0616027231', warehouse='FG to Sell Warehouse - AMB-W', actual_qty=100),
            MagicMock(item_code='ITEM_0612200241', warehouse='FG to Sell Warehouse - AMB-W', actual_qty=200),
            MagicMock(item_code='ITEM_0616050231', warehouse='FG to Sell Warehouse - AMB-W', actual_qty=150),
        ]
        
        # Mock batch data
        mock_batch = [MagicMock(name='LOTE001', batch_qty=100, expiry_date='2025-12-31')]
        
        self.frappe_mock.get_all.side_effect = lambda doctype, **kwargs: {
            'Bin': mock_bins,
            'Batch': mock_batch,
        }.get(doctype, [])
        
        # Call with product filter
        result = self.reader_module.get_available_batches(product_code='0616')
        
        # Should only include 0616 products (2 items)
        self.assertEqual(len(result), 2)
        for item in result:
            self.assertEqual(item['product'], '0616')
    
    def test_get_available_batches_sorted_by_fefo(self):
        """Test that results are sorted by FEFO key (oldest first)."""
        # Mock Bin data - intentionally out of order
        mock_bins = [
            MagicMock(item_code='ITEM_0616050241', warehouse='FG to Sell Warehouse - AMB-W', actual_qty=100),  # FEFO 24050
            MagicMock(item_code='ITEM_0616027231', warehouse='FG to Sell Warehouse - AMB-W', actual_qty=200),  # FEFO 23027 (oldest)
            MagicMock(item_code='ITEM_0616100251', warehouse='FG to Sell Warehouse - AMB-W', actual_qty=150),  # FEFO 25100 (newest)
        ]
        
        mock_batch = [MagicMock(name='LOTE001', batch_qty=100, expiry_date='2025-12-31')]
        
        self.frappe_mock.get_all.side_effect = lambda doctype, **kwargs: {
            'Bin': mock_bins,
            'Batch': mock_batch,
        }.get(doctype, [])
        
        result = self.reader_module.get_available_batches(product_code='0616')
        
        # Verify sorted by FEFO key
        fefo_keys = [item['fefo_key'] for item in result]
        self.assertEqual(fefo_keys, sorted(fefo_keys))
        
        # Verify order: 23027 < 24050 < 25100
        self.assertEqual(result[0]['fefo_key'], 23027)
        self.assertEqual(result[1]['fefo_key'], 24050)
        self.assertEqual(result[2]['fefo_key'], 25100)


# ===========================================
# Test 4: COA Parameters (from spec section 4.3)
# ===========================================

class TestGetBatchCOAParameters(unittest.TestCase):
    """
    Test COA parameter retrieval using 'specification' field.
    
    Uses COA AMB doctype and 'COA Quality Test Parameter' child table.
    """
    
    def setUp(self):
        """Set up test fixtures with mocked frappe."""
        self.frappe_mock = MagicMock()
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': self.frappe_mock})
        self.frappe_patcher.start()
        
        import raven_ai_agent.skills.formulation_reader.reader as reader_module
        self.reader_module = reader_module
        reader_module.frappe = self.frappe_mock
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_get_coa_parameters_uses_specification_field(self):
        """Verify that 'specification' field is used as parameter name."""
        # Mock COA lookup
        mock_coa = [MagicMock(name='COA-AMB-001')]
        
        # Mock parameters with 'specification' field (per spec)
        mock_params = [
            MagicMock(specification='pH', result='3.6', min_value=3.4, max_value=3.8, status='PASS'),
            MagicMock(specification='Polysaccharides', result='8.5', min_value=8.0, max_value=9.0, status='PASS'),
            MagicMock(specification='Ash', result='2.1', min_value=None, max_value=3.0, status='PASS'),
        ]
        
        def mock_get_all(doctype, **kwargs):
            if doctype == 'COA AMB':
                return mock_coa
            elif doctype == 'COA Quality Test Parameter':
                return mock_params
            return []
        
        self.frappe_mock.get_all.side_effect = mock_get_all
        
        result = self.reader_module.get_batch_coa_parameters('LOTE040')
        
        # Verify parameters are keyed by 'specification' field
        self.assertIn('pH', result)
        self.assertIn('Polysaccharides', result)
        self.assertIn('Ash', result)
        
        # Verify values are converted to float
        self.assertEqual(result['pH']['value'], 3.6)
        self.assertEqual(result['Polysaccharides']['value'], 8.5)
    
    def test_get_coa_parameters_returns_none_when_not_found(self):
        """Return None when COA doesn't exist."""
        self.frappe_mock.get_all.return_value = []
        
        result = self.reader_module.get_batch_coa_parameters('NONEXISTENT')
        
        self.assertIsNone(result)


# ===========================================
# Test 5: TDS Compliance (from spec section 4.4)
# ===========================================

class TestCheckTDSCompliance(unittest.TestCase):
    """
    Test check_tds_compliance function as per spec section 4.4.
    
    Returns dict with compliance status per parameter:
    - PASS: value within range
    - BELOW_MIN: value < min
    - ABOVE_MAX: value > max
    - MISSING: parameter not in batch_params
    - NO_VALUE: parameter exists but value is None
    """
    
    def setUp(self):
        """Set up test fixtures with mocked frappe."""
        self.frappe_mock = MagicMock()
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': self.frappe_mock})
        self.frappe_patcher.start()
        
        from raven_ai_agent.skills.formulation_reader.reader import check_tds_compliance
        self.check_tds_compliance = check_tds_compliance
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_all_pass_when_within_range(self):
        """All parameters within range should return all_pass=True."""
        batch_params = {
            'pH': {'value': 3.6, 'min': 3.4, 'max': 3.8, 'status': 'PASS'},
            'Polysaccharides': {'value': 8.5, 'min': 8.0, 'max': 9.0, 'status': 'PASS'},
        }
        
        tds_spec = {
            'pH': {'min': 3.4, 'max': 3.8},
            'Polysaccharides': {'min': 8.0, 'max': 9.0},
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertTrue(result['all_pass'])
        self.assertEqual(result['parameters']['pH']['status'], 'PASS')
        self.assertEqual(result['parameters']['Polysaccharides']['status'], 'PASS')
    
    def test_below_min_status(self):
        """Value below min should return BELOW_MIN status."""
        batch_params = {
            'pH': {'value': 3.2, 'min': 3.4, 'max': 3.8, 'status': 'FAIL'},
        }
        
        tds_spec = {
            'pH': {'min': 3.4, 'max': 3.8},
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertFalse(result['all_pass'])
        self.assertEqual(result['parameters']['pH']['status'], 'BELOW_MIN')
    
    def test_above_max_status(self):
        """Value above max should return ABOVE_MAX status."""
        batch_params = {
            'pH': {'value': 4.0, 'min': 3.4, 'max': 3.8, 'status': 'FAIL'},
        }
        
        tds_spec = {
            'pH': {'min': 3.4, 'max': 3.8},
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertFalse(result['all_pass'])
        self.assertEqual(result['parameters']['pH']['status'], 'ABOVE_MAX')
    
    def test_missing_parameter_status(self):
        """Missing parameter should return MISSING status."""
        batch_params = {
            'pH': {'value': 3.6, 'min': 3.4, 'max': 3.8, 'status': 'PASS'},
        }
        
        tds_spec = {
            'pH': {'min': 3.4, 'max': 3.8},
            'Polysaccharides': {'min': 8.0, 'max': 9.0},  # Not in batch_params
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertFalse(result['all_pass'])
        self.assertEqual(result['parameters']['Polysaccharides']['status'], 'MISSING')
    
    def test_no_value_status(self):
        """Parameter with None value should return NO_VALUE status."""
        batch_params = {
            'pH': {'value': None, 'min': 3.4, 'max': 3.8, 'status': 'PENDING'},
        }
        
        tds_spec = {
            'pH': {'min': 3.4, 'max': 3.8},
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertFalse(result['all_pass'])
        self.assertEqual(result['parameters']['pH']['status'], 'NO_VALUE')
    
    def test_only_min_specified(self):
        """Test compliance with only min specified."""
        batch_params = {
            'Polysaccharides': {'value': 8.5, 'min': 8.0, 'max': None, 'status': 'PASS'},
        }
        
        tds_spec = {
            'Polysaccharides': {'min': 8.0},  # No max
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertTrue(result['all_pass'])
        self.assertEqual(result['parameters']['Polysaccharides']['status'], 'PASS')
    
    def test_only_max_specified(self):
        """Test compliance with only max specified."""
        batch_params = {
            'Ash': {'value': 2.5, 'min': None, 'max': 3.0, 'status': 'PASS'},
        }
        
        tds_spec = {
            'Ash': {'max': 3.0},  # No min
        }
        
        result = self.check_tds_compliance(batch_params, tds_spec)
        
        self.assertTrue(result['all_pass'])
        self.assertEqual(result['parameters']['Ash']['status'], 'PASS')


# ===========================================
# Legacy Tests (preserved from original)
# ===========================================

class TestFormulationReaderSkill(unittest.TestCase):
    """Test the FormulationReaderSkill query handling."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': MagicMock()})
        self.frappe_patcher.start()
        
        from raven_ai_agent.skills.formulation_reader.skill import FormulationReaderSkill
        self.skill = FormulationReaderSkill()
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_can_handle_batch_query(self):
        """Test detection of batch-related queries."""
        queries = [
            "Show batches for item 0227-0303 in Almacen-MP",
            "List all batches in warehouse WH-001",
            "Get batch data for item AL-QX-90-10",
            "What batches do we have available for product 0612?",  # From spec example 5.1
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")
            self.assertGreater(confidence, 0.5)
    
    def test_can_handle_coa_query(self):
        """Test detection of COA-related queries."""
        queries = [
            "Get COA for batch BATCH-AMB-2024-001",
            "Show analytical parameters for batch X",
            "What is the pH value for batch Y",
            "Show me the COA parameters for batch LOTE040",  # From spec example 5.2
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")
    
    def test_can_handle_fefo_query(self):
        """Test detection of FEFO-related queries (from spec examples)."""
        queries = [
            "Which batches from 2023 still have stock?",  # From spec example 5.3
            "What is the oldest batch we should use first?",  # From spec example 5.4
        ]
        
        for query in queries:
            can_handle, confidence = self.skill.can_handle(query)
            self.assertTrue(can_handle, f"Should handle: {query}")


class TestWeightedAverageCalculation(unittest.TestCase):
    """TC1.3: Test weighted average calculation accuracy."""
    
    def test_simple_weighted_average(self):
        """Test weighted average calculation matches manual Excel calculation."""
        # Given: Two cunetes with pH values
        # Cunete 1: pH 3.5, mass 10 kg
        # Cunete 2: pH 3.7, mass 15 kg
        # Expected: (3.5 * 10 + 3.7 * 15) / (10 + 15) = (35 + 55.5) / 25 = 3.62
        
        values = [(3.5, 10.0), (3.7, 15.0)]
        total_weighted = sum(v * m for v, m in values)
        total_mass = sum(m for _, m in values)
        predicted = total_weighted / total_mass
        
        self.assertAlmostEqual(predicted, 3.62, places=2)
    
    def test_weighted_average_with_three_inputs(self):
        """Test weighted average with three cunetes."""
        # Cunete 1: polysaccharides 8.2, mass 10 kg
        # Cunete 2: polysaccharides 8.5, mass 20 kg
        # Cunete 3: polysaccharides 7.8, mass 5 kg
        # Expected: (8.2*10 + 8.5*20 + 7.8*5) / (10+20+5) = 291/35 ≈ 8.314
        
        values = [(8.2, 10.0), (8.5, 20.0), (7.8, 5.0)]
        total_weighted = sum(v * m for v, m in values)
        total_mass = sum(m for _, m in values)
        predicted = total_weighted / total_mass
        
        self.assertAlmostEqual(predicted, 8.314, places=2)


class TestTDSPassFailLogic(unittest.TestCase):
    """TC1.4: Test PASS/FAIL determination against TDS ranges."""
    
    def test_pass_within_range(self):
        """Value within TDS range should PASS."""
        predicted = 3.6
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertTrue(passes)
    
    def test_fail_below_min(self):
        """Value below TDS min should FAIL."""
        predicted = 3.2
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertFalse(passes)
    
    def test_fail_above_max(self):
        """Value above TDS max should FAIL."""
        predicted = 4.0
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertFalse(passes)
    
    def test_pass_at_boundary_min(self):
        """Value at TDS min boundary should PASS."""
        predicted = 3.4
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertTrue(passes)
    
    def test_pass_at_boundary_max(self):
        """Value at TDS max boundary should PASS."""
        predicted = 3.8
        tds_min = 3.4
        tds_max = 3.8
        
        passes = tds_min <= predicted <= tds_max
        self.assertTrue(passes)


class TestDataClasses(unittest.TestCase):
    """Test data class structures."""
    
    def setUp(self):
        """Set up with mocked frappe."""
        self.frappe_patcher = patch.dict('sys.modules', {'frappe': MagicMock()})
        self.frappe_patcher.start()
    
    def tearDown(self):
        """Clean up after tests."""
        self.frappe_patcher.stop()
    
    def test_blend_input_creation(self):
        """Test BlendInput dataclass."""
        from raven_ai_agent.skills.formulation_reader.reader import BlendInput
        
        inp = BlendInput(cunete_id="BATCH-001-C1", mass_kg=10.0)
        self.assertEqual(inp.cunete_id, "BATCH-001-C1")
        self.assertEqual(inp.mass_kg, 10.0)
    
    def test_tds_parameter_defaults(self):
        """Test TDSParameter default values."""
        from raven_ai_agent.skills.formulation_reader.reader import TDSParameter
        
        param = TDSParameter(parameter_code="ph", parameter_name="pH")
        self.assertIsNone(param.min_value)
        self.assertIsNone(param.max_value)
        self.assertTrue(param.is_critical)
    
    def test_coa_parameter_creation(self):
        """Test COAParameter dataclass."""
        from raven_ai_agent.skills.formulation_reader.reader import COAParameter
        
        param = COAParameter(
            parameter_code="ph",
            parameter_name="pH",
            average=3.6,
            min_value=3.4,
            max_value=3.8,
            result="PASS"
        )
        self.assertEqual(param.average, 3.6)
        self.assertEqual(param.result, "PASS")


# Golden Test Data (from historical formulations)
GOLDEN_TEST_DATA = {
    "test_1": {
        "description": "Simple 2-cunete blend for AL-QX-90-10",
        "inputs": [
            {"cunete_id": "BATCH-2024-001-C1", "mass_kg": 300.0, "ph": 3.5, "polysaccharides": 8.2},
            {"cunete_id": "BATCH-2024-002-C1", "mass_kg": 400.0, "ph": 3.7, "polysaccharides": 8.4},
        ],
        "target_item": "AL-QX-90-10",
        "tds": {"ph": {"min": 3.4, "max": 3.9}, "polysaccharides": {"min": 8.0, "max": 9.0}},
        "expected": {
            "ph": 3.614,  # (3.5*300 + 3.7*400) / 700
            "polysaccharides": 8.314,  # (8.2*300 + 8.4*400) / 700
            "all_pass": True,
        }
    }
}


class TestGoldenTests(unittest.TestCase):
    """Golden tests using historical formulation data."""
    
    def test_golden_blend_calculation(self):
        """Verify weighted averages match expected values from golden test data."""
        test = GOLDEN_TEST_DATA["test_1"]
        
        # Calculate weighted averages
        total_mass = sum(inp["mass_kg"] for inp in test["inputs"])
        
        ph_weighted = sum(inp["ph"] * inp["mass_kg"] for inp in test["inputs"])
        poly_weighted = sum(inp["polysaccharides"] * inp["mass_kg"] for inp in test["inputs"])
        
        predicted_ph = ph_weighted / total_mass
        predicted_poly = poly_weighted / total_mass
        
        # Verify against expected
        self.assertAlmostEqual(predicted_ph, test["expected"]["ph"], places=3)
        self.assertAlmostEqual(predicted_poly, test["expected"]["polysaccharides"], places=3)
        
        # Verify PASS/FAIL
        ph_passes = test["tds"]["ph"]["min"] <= predicted_ph <= test["tds"]["ph"]["max"]
        poly_passes = test["tds"]["polysaccharides"]["min"] <= predicted_poly <= test["tds"]["polysaccharides"]["max"]
        
        self.assertTrue(ph_passes)
        self.assertTrue(poly_passes)
        self.assertEqual(ph_passes and poly_passes, test["expected"]["all_pass"])


if __name__ == "__main__":
    unittest.main()
