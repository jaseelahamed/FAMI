"""Regression checks for isolated font-heading measurements."""
import unittest
from unittest.mock import patch
import numpy as np
from font_regions import compact_brand, measure_heading_pair
from app import MedicineLabelValidator


class FontRegionTests(unittest.TestCase):
    def test_names_without_strength_and_mixed_case_are_candidates(self):
        for name in ('Medifor', 'Medifor-40', 'MEDIFOR-PN Tablets', 'Medifor-Forte'):
            self.assertTrue(compact_brand(name), name)

    def test_identifiers_and_body_text_are_not_brands(self):
        for text in ('MIg.LIoNo.MLF282025JK0000Q2&', 'MLF252025JK000003',
                     'Composition:', 'Tablets IP', 'Mfg licence 1234', 'Marketed By'):
            self.assertFalse(compact_brand(text), text)

    def test_centered_brand_can_be_wider_than_tablets_line(self):
        rows=[{'text':t,'box':box,'source':'paddle'} for t,box in [
            ('Genericname',[20,20,500,70]), ('Tablets',[200,100,140,60]),
            ('Medifor-Forte',[80,175,400,60]), ('Composition:',[20,255,200,20]),
            ('Each tablet contains:',[20,285,300,20]), ('Excipients',[20,315,200,20])]]
        def measured(image,box,name,backend,scale):
            return {'name':name,'height_px':30 if name=='Medifor-Forte' else 40,
                    'confidence':95,'words':[],'region':box}
        with patch('font_regions.read_region',side_effect=measured):
            result=measure_heading_pair(np.zeros((400,600,3),dtype=np.uint8),rows,None,1)
        self.assertEqual(result['brand']['name'],'Medifor-Forte')
        self.assertEqual(result['generic']['name'],'Genericname')

    def test_measurement_can_fail_comparison_without_being_missing(self):
        validator=MedicineLabelValidator.__new__(MedicineLabelValidator)
        validator.font_heading_pair={'source':'tesseract_heading_crops',
            'generic':{'name':'Genericname','height_px':20},
            'brand':{'name':'Medifor','height_px':30}}
        result=validator.evaluate_font_size_rule('unrelated','identifier')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['ratio'],.67)
        self.assertEqual(result['brand_name'],'Medifor')
        self.assertNotIn('Unable',result['details'])

    def test_no_regions_produces_no_invented_measurement(self):
        self.assertIsNone(measure_heading_pair(np.zeros((100,100,3),dtype=np.uint8),[],None,1))


if __name__=='__main__':unittest.main()
