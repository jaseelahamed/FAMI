"""Regression checks for OCR evidence handling and bounded field extraction."""
import unittest
import os
from unittest.mock import patch

from app import MedicineLabelValidator
from label_fields import extract_fields, normalize_composition
from ocr_pipeline import _read_lines, recover_rx_symbol


class LabelValidationTests(unittest.TestCase):
    def validator(self):
        validator = MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.ocr_data = None
        validator.ocr_lines = []
        validator.barcode_results = {}
        validator.redline_results = {}
        return validator

    def test_sections_do_not_bleed_into_neighbor_fields(self):
        text = """Clindamycin Capsules I.P.
DALACIN C® 300 mg
For dosage, use and other information about the
product, please refer to the package insert.
Store below 30°C.
Keep out of reach of children.
Each hard gelatin capsule contains:
Clindamycin Hydrochloride I.P. equivalent to
Clindamycin 300mg
Excipients q.s.
Import Licence No.: FF-307-30369
Manufactured by: FAREVA AMBOISE, Zone industrielle,
29 route des Industries, 37530 POCE Sur CISSE - France
Imported and marketed by: Pfizer Products India Private Limited
"""
        fields = extract_fields(text)
        self.assertEqual(fields['generic']['value'], 'Clindamycin')
        self.assertEqual(fields['brand']['value'], 'DALACIN C')
        self.assertNotIn('Store', fields['dosage']['value'])
        self.assertNotIn('Each', fields['storage']['value'])
        self.assertNotIn('Excipients', fields['active']['value'])
        self.assertIn('300mg', fields['active']['value'])
        self.assertNotIn('Pfizer', fields['manufacturer']['value'])
        self.assertIn('France', fields['manufacturer']['value'])
        self.assertIn('FF-307-30369', fields['licence']['value'])

    def test_partial_date_text_passes_presence_check(self):
        report = self.validator().validate_regulatory_fields('Exp 06-2030')
        self.assertEqual(report['field_checks']['Mfg Date / Expiry Date']['status'], 'PASS')

    def test_missing_font_measurements_are_not_invented(self):
        result = self.validator().evaluate_font_size_rule('Clindamycin', 'DALACIN')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIsNone(result['ratio'])
        self.assertEqual(result['brand_font_height_px'], 0)

    def test_visible_undecoded_qr_passes_presence_check(self):
        validator = self.validator()
        validator.barcode_results = {'detected': True, 'decoded': False}
        report = validator.validate_regulatory_fields('')
        self.assertEqual(report['field_checks']['Required Barcode or QR Code']['status'], 'PASS')
        self.assertFalse(validator.barcode_results['decoded'])

    def test_identifier_presence_passes_despite_ocr_disagreement(self):
        validator = self.validator()
        validator.ocr_lines = [{
            'text': 'Import Licence No.: FF-207-30369', 'confidence': 90,
            'alternatives': [{'text': 'Import Licence No.: FF-307-30369', 'confidence': 80}]
        }]
        report = validator.validate_regulatory_fields(validator.ocr_lines[0]['text'])
        field = report['field_checks']['Mfg License Number']
        self.assertEqual(field['status'], 'PASS')
        self.assertEqual(field['review_notes'], [])
        self.assertIn('FF-307-30369', validator.ocr_lines[0]['alternatives'][0]['text'])

    def test_missing_presence_fields_do_not_pass(self):
        fields = self.validator().validate_regulatory_fields('')['field_checks']
        for key in ('Batch / Lot Number', 'Directions for Use / Dosage', 'Mfg License Number',
                    'Name and Address of Manufacturer', 'Schedule Warning (Prescription Drugs)'):
            self.assertEqual(fields[key]['status'], 'FAIL')
            self.assertEqual(fields[key]['presence_state'], 'not_detected')
        self.assertEqual(fields['Required Barcode or QR Code']['status'], 'OPTIONAL')

    def test_uncertain_content_passes_with_diagnostics(self):
        validator = self.validator()
        text = 'Each tablet contains: Ciprofloxacin 500 mg'
        validator.ocr_lines = [{'text': text, 'confidence': 65,
            'alternatives': [{'text': 'Each tablet contains: Ciprofloxacin 300 mg', 'confidence': 90}]}]
        report = validator.validate_regulatory_fields(text)
        field = report['field_checks']['Active Ingredients in Metric Units']
        self.assertEqual(field['status'], 'PASS')
        self.assertTrue(any('Low OCR' in note for note in field['diagnostic_notes']))
        self.assertTrue(any('disagree' in note for note in field['diagnostic_notes']))
        self.assertFalse(report['requires_review'])
        self.assertEqual({f['status'] for f in report['field_checks'].values()}, {'PASS', 'FAIL', 'OPTIONAL'})

    def test_missing_mandatory_fields_fail_and_optional_fields_are_neutral(self):
        report = self.validator().validate_regulatory_fields('')
        self.assertEqual(len(report['field_checks']), 14)
        self.assertTrue(all(f['status'] == ('FAIL' if f['required'] else 'OPTIONAL')
                            for f in report['field_checks'].values()))
        self.assertEqual(report['passed_required'], '0/12')
        self.assertFalse(report['requires_review'])
        self.assertEqual(report['overall_status'], 'NON-COMPLIANT / REJECT')

    def test_optional_detections_do_not_change_mandatory_score(self):
        validator = self.validator()
        absent = validator.validate_regulatory_fields('')
        validator.barcode_results = {'detected': True}
        present = validator.validate_regulatory_fields('Rx')
        for name in ('Prescription Symbol (Rx, NRx, XRx)', 'Required Barcode or QR Code'):
            self.assertFalse(present['field_checks'][name]['required'])
            self.assertEqual(present['field_checks'][name]['status'], 'PASS')
            self.assertEqual(absent['field_checks'][name]['status'], 'OPTIONAL')
        self.assertEqual(absent['score_percentage'], present['score_percentage'])
        self.assertEqual(absent['overall_status'], present['overall_status'])

    def test_composition_spelling_uses_generic_and_preserves_quantity(self):
        raw = 'Each hard geiatin capsuie contains: Cli ivamycin Hydrochloride |.P. equivalent to Clindamycin wu... 300mg SO'
        corrected = normalize_composition(raw, 'Clindamycin')
        self.assertIn('hard gelatin capsule', corrected)
        self.assertIn('Clindamycin Hydrochloride I.P.', corrected)
        self.assertIn('300mg', corrected)
        self.assertNotIn('wu...', corrected)
        self.assertTrue(corrected.endswith('Clindamycin 300mg'))
        self.assertEqual(normalize_composition('Amoxicillin Hydrochloride 250mg', 'Clindamycin'),
                         'Amoxicillin Hydrochloride 250mg')

    def test_ix_in_body_text_is_not_changed_to_rx(self):
        import numpy as np
        import pytesseract
        lines = [{'text': 'IX', 'words': [{'text': 'IX', 'left': 20, 'top': 700,
                                         'width': 70, 'height': 90}], 'alternatives': []}]
        with patch.object(pytesseract, 'image_to_string') as read:
            recover_rx_symbol(np.full((1000, 600, 3), 255, dtype=np.uint8), lines, pytesseract)
        read.assert_not_called()
        self.assertEqual(lines[0]['text'], 'IX')

    def test_ocr_line_numbers_are_scoped_to_blocks(self):
        import pytesseract
        data = {'text': ['Batch', 'AB123', 'Store', 'below'],
                'conf': [95] * 4, 'block_num': [1, 1, 2, 2],
                'par_num': [1] * 4, 'line_num': [1] * 4,
                'left': [0, 60, 0, 60], 'top': [0, 0, 50, 50],
                'width': [50] * 4, 'height': [20] * 4}
        with patch.object(pytesseract, 'image_to_data', return_value=data):
            lines = _read_lines(None, pytesseract, 'test')
        self.assertEqual([line['text'] for line in lines], ['Batch AB123', 'Store below'])

    @unittest.skipUnless(os.environ.get('RUN_OCR_INTEGRATION') == '1', 'Set RUN_OCR_INTEGRATION=1 for the photo regression')
    def test_supplied_photo(self):
        from pathlib import Path
        photo = Path(__file__).parent / 'static/uploads/test2.jpeg'
        validator = MedicineLabelValidator(str(photo))
        report = validator.run_full_pipeline()
        fields = report['regulatory_validation']['field_checks']
        expected = {
            'Generic Name': 'Clindamycin',
            'Batch / Lot Number': 'C127302',
            'Mfg Date / Expiry Date': '06-2030',
            'Dosage Form and Strength': '300 mg',
            'Active Ingredients in Metric Units': '300mg',
            'Storage Conditions': '30°C',
            'Name and Address of Manufacturer': 'FAREVA AMBOISE',
            'Schedule Warning (Prescription Drugs)': 'SCHEDULE H',
        }
        for field, value in expected.items():
            with self.subTest(field=field):
                self.assertIn(value, fields[field]['extracted_value'])
        for field in ('Directions for Use / Dosage', 'Batch / Lot Number', 'Mfg License Number',
                      'Name and Address of Manufacturer', 'Schedule Warning (Prescription Drugs)',
                      'Required Barcode or QR Code', 'Prescription Symbol (Rx, NRx, XRx)'):
            with self.subTest(status=field):
                self.assertEqual(fields[field]['status'], 'PASS')
        self.assertIn('Clindamycin Hydrochloride I.P.', fields['Active Ingredients in Metric Units']['extracted_value'])
        self.assertFalse(report['regulatory_validation']['requires_review'])
        self.assertFalse(report['barcode_detection']['gs1_verified'])


class PaddleRoutingTests(unittest.TestCase):
    def validator(self):
        import numpy as np
        validator = MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.original_image = validator.full_res_image = np.zeros((100, 200, 3), dtype=np.uint8)
        return validator

    def test_default_paddle_preserves_evidence_without_tesseract(self):
        row = {"text": "Batch ABC123 Exp 06/2030", "confidence": 95,
               "box": [10, 20, 100, 15], "source": "paddle", "words": [], "alternatives": []}
        with patch.dict(os.environ, {}, clear=True), \
             patch('ocr_paddle.extract_lines', return_value=([row], [])), \
             patch('ocr_pipeline.extract_lines') as fallback, \
             patch('app.PYTESSERACT_AVAILABLE', False):
            validator = self.validator()
            self.assertEqual(validator.extract_text(), row['text'])
            self.assertEqual(validator.ocr_engine, 'paddle')
            self.assertEqual(validator.ocr_lines[0]['box'], row['box'])
            fallback.assert_not_called()
            self.assertEqual(validator.evaluate_font_size_rule('Generic', 'Brand')['status'], 'FAIL')

    def test_empty_paddle_falls_back_with_warning(self):
        row = {"text": "Batch ABC123 Exp 06/2030", "confidence": 90,
               "box": [0, 0, 100, 10], "source": "gray", "words": [], "alternatives": []}
        with patch.dict(os.environ, {'OCR_ENGINE': 'paddle'}), \
             patch('ocr_paddle.extract_lines', return_value=([], ['Paddle unavailable'])), \
             patch('ocr_pipeline.extract_lines', return_value=([row], [])):
            validator = self.validator()
            self.assertEqual(validator.extract_text(), row['text'])
            self.assertEqual(validator.ocr_engine, 'tesseract')
            self.assertIn('Paddle unavailable', validator.ocr_warnings)

    def test_paddle_rotation_maps_boxes_back(self):
        import ocr_paddle
        validator = self.validator()
        with patch.dict(os.environ, {'PADDLE_ROTATED': 'always'}), \
             patch('ocr_paddle._get_engine', return_value=object()), \
             patch('ocr_paddle._run', side_effect=[[], [('Batch ABC123', .95, (10, 20, 70, 40))]]):
            rows, warnings = ocr_paddle.extract_lines(validator.full_res_image)
        self.assertEqual(warnings, [])
        self.assertEqual(rows[0]['box'], [20, 30, 20, 60])
        self.assertEqual(rows[0]['confidence'], 95)


class FontOnlyTesseractTests(unittest.TestCase):
    def test_font_pass_does_not_change_paddle_fields(self):
        import copy
        import numpy as np
        row = {"text": "Ciprofloxacin tablets IP 500mg", "confidence": 95,
               "box": [0, 0, 180, 30], "source": "paddle", "words": [], "alternatives": []}
        font_rows = [{"text": "CIPRODAC 500", "words": [
            {"text": "CIPRODAC", "height": 22, "confidence": 95}]},
            {"text": "CIPROFLOXACIN TABLETS IP 500MG", "words": [
            {"text": "CIPROFLOXACIN", "height": 27, "confidence": 95}]}]
        validator = MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.original_image = validator.full_res_image = np.zeros((100, 200, 3), dtype=np.uint8)
        validator.barcode_results = {}
        validator.redline_results = {}
        with patch.dict(os.environ, {'OCR_ENGINE': 'paddle'}), \
             patch('ocr_paddle.extract_lines', return_value=([copy.deepcopy(row)], [])), \
             patch('app.PYTESSERACT_AVAILABLE', True), \
             patch('ocr_quantity.recover_quantities', return_value=[]), \
             patch('ocr_pipeline._read_lines', return_value=font_rows):
            text = validator.extract_text()
        self.assertEqual(text, row['text'])
        self.assertEqual(validator.ocr_lines, [row])
        self.assertEqual(validator.ocr_data['text'], [])
        after = validator.validate_regulatory_fields(text)
        self.assertEqual(validator.font_ratio_results['ratio'], 1.23)
        self.assertEqual(validator.font_ratio_results['brand_name'], 'CIPRODAC')
        validator.font_ocr_data = None
        validator.font_ocr_names = {}
        before = validator.validate_regulatory_fields(text)
        font = 'Generic Font Size >= Brand (Rule 96(1)(i))'
        self.assertEqual(after['field_checks'][font]['status'], 'PASS')
        self.assertEqual(before['field_checks'][font]['status'], 'FAIL')
        for name in before['field_checks']:
            if name != font:
                self.assertEqual(before['field_checks'][name], after['field_checks'][name], name)

    def test_failed_font_backend_does_not_abort_scan(self):
        import numpy as np
        validator = MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.original_image = np.zeros((100, 200, 3), dtype=np.uint8)
        validator.ocr_data = None
        validator.ocr_engine = 'paddle'
        with patch('app.PYTESSERACT_AVAILABLE', True), \
             patch('ocr_pipeline._read_lines', side_effect=RuntimeError('OCR timeout')):
            validator.measure_font_words()
        result = validator.evaluate_font_size_rule('Ciprofloxacin', 'CIPRODAC')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('OCR timeout', result['details'])

    def test_smaller_generic_still_fails(self):
        validator = MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.ocr_data = {'text': ['CIPRODAC', 'Ciprofloxacin'],
                              'height': [30, 20], 'conf': [95, 95]}
        self.assertEqual(validator.evaluate_font_size_rule('Ciprofloxacin', 'CIPRODAC')['status'], 'FAIL')


class QuantityRecoveryTests(unittest.TestCase):
    def recover(self, reading, confidences=None, original='Ciprofloxacin tablets IP SOOMG'):
        import numpy as np
        from unittest.mock import Mock
        from ocr_quantity import recover_quantities
        backend = Mock()
        tokens = reading.split()
        backend.image_to_data.return_value = {'text': tokens, 'conf': confidences or [95]*len(tokens)}
        row = {'text': original, 'source': 'paddle', 'box': [0, 0, 100, 20],
               'confidence': 96, 'words': [], 'alternatives': []}
        recover_quantities(np.zeros((30, 120, 3), dtype=np.uint8), [row], backend)
        return row, backend

    def test_confirmed_quantity_supplies_form_and_active_strength(self):
        row, _ = self.recover('Each tablet contains: Ciprofloxacin 500 mg',
                              original='Each tablet contains: Ciprofloxacin 5OO mg')
        self.assertIn('500 mg', row['text'])
        self.assertIn('5OO mg', row['original_text'])
        self.assertEqual(row['quantity_corrections'][0]['source'], 'tesseract_quantity_crop')
        fields = extract_fields(row['text'])
        self.assertNotIn('strength', fields)
        self.assertIn('500 mg', fields['active']['value'])
        self.assertFalse(fields['active'].get('uncertain', False))

    def test_conflicting_quantity_is_not_substituted(self):
        row, _ = self.recover('Ciprofloxacin tablets IP 300MG')
        self.assertIn('SOOMG', row['text'])
        self.assertNotIn('quantity_corrections', row)

    def test_low_confidence_quantity_remains_unresolved(self):
        row, _ = self.recover('Ciprofloxacin tablets IP 500MG', [95, 95, 95, 60])
        self.assertIn('SOOMG', row['text'])

    def test_clear_quantity_does_not_trigger_retry(self):
        row, backend = self.recover('unused', original='Ciprofloxacin tablets IP 500MG')
        backend.image_to_data.assert_not_called()
        self.assertNotIn('original_text', row)


class PhotoAuditRegressionTests(unittest.TestCase):
    def test_licence_cannot_be_a_manufacturing_date(self):
        fields=extract_fields('Mfg.LicNo.89/UA/SC/P-2016\nEXP.JAN.2028')
        self.assertNotIn('mfg_date',fields)
        self.assertIn('licence',fields)

    def test_glued_batch_and_dates_are_separated(self):
        fields=extract_fields('B.No.LV25DT-127BMFG.04/2025EXP.03/2027')
        self.assertEqual(fields['batch']['value'],'B.No.LV25DT-127B')
        self.assertEqual(fields['mfg_date']['value'],'MFG.04/2025')
        self.assertEqual(fields['exp_date']['value'],'EXP.03/2027')

    def test_colours_and_dosage_prose_are_not_generic_names(self):
        fields=extract_fields('Colors used in capsule shell Titanium dioxide\nDo not crush or chew the tablet')
        self.assertNotIn('generic',fields)

    def test_composition_quantities_stay_in_active_ingredients(self):
        fields=extract_fields('Each uncoated tablet contains\nTelmisartan I.P. 40mg.\nExcipients q.s.')
        self.assertNotIn('strength', fields)
        self.assertIn('40mg',fields['active']['value'])
        self.assertIn('Telmisartan',fields['generic']['value'])

    def test_composition_does_not_populate_form_strength(self):
        text = 'Pregabalin tablets\nComposition:\nEach tablet contains:\nPregabalin 75mg\nNortriptyline 10mg'
        fields = extract_fields(text)
        self.assertNotIn('strength', fields)
        self.assertIn('75mg', fields['active']['value'])
        self.assertIn('10mg', fields['active']['value'])
        validator = LabelValidationTests().validator()
        check = validator.validate_regulatory_fields(text)['field_checks']['Dosage Form and Strength']
        self.assertEqual(check['extracted_value'], 'tablets')
        self.assertEqual(check['status'], 'PASS')

    def test_heading_strength_is_not_overwritten_by_composition(self):
        text = 'Ciprofloxacin tablets IP 500MG\nEach tablet contains: Ciprofloxacin Hydrochloride 582mg equivalent to Ciprofloxacin 500mg'
        fields = extract_fields(text)
        self.assertEqual(fields['strength']['value'], '500MG')
        self.assertEqual(fields['strength']['lines'], [text.splitlines()[0]])
        self.assertIn('582mg', fields['active']['value'])

    def test_combination_strength_explicitly_in_heading_is_preserved(self):
        fields = extract_fields('Pregabalin & Nortriptyline tablets 75mg + 10mg')
        self.assertEqual(fields['strength']['value'], '75mg + 10mg')

    def test_enzyme_units_are_not_fabricated_as_milligrams(self):
        fields=extract_fields('Composition:\nEach Enteric coated tablet contains\n2 lack armour units of enzymatic activity\nExcipients')
        self.assertTrue(fields['active']['uncertain'])
        self.assertNotIn('strength', fields)
        self.assertIn('2 lack armour units',fields['active']['value'])

    def test_photo_qr_presence_and_red_markings(self):
        import json
        from pathlib import Path
        reference=Path('testing_results/visual_reference.json')
        if not reference.exists():
            self.skipTest('Local photo reference is unavailable')
        for row in json.loads(reference.read_text())['images']:
            path=Path('static/uploads/TestingMedicineLabels')/row['image']
            if not path.exists():
                self.skipTest('Local test photos are unavailable')
            with self.subTest(image=row['image']):
                validator=MedicineLabelValidator(str(path))
                self.assertEqual(validator.detect_barcode_or_qr()['detected'],
                    row['presence']['Required Barcode or QR Code']=='visible')
                self.assertTrue(validator.detect_redline()['detected'])


if __name__ == '__main__':
    unittest.main()
