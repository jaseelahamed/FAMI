"""Regression tests for manufacturer/date recovery and visual panel presence."""
import unittest
from unittest.mock import patch
import numpy as np
import cv2
from label_fields import extract_fields
from field_recovery import recover_fields
from warning_panel import detect_warning_panel


class FieldRecoveryTests(unittest.TestCase):
    def test_manufacturing_header_ocr_and_punctuation(self):
        for text in ('Mariutactured in India by:', 'Manulactured in Indla by', 'Mfg.by:'):
            fields=extract_fields(text+'\nExample Labs Pvt. Ltd.\nPlot 12, Industrial Area')
            self.assertIn('Example Labs',fields['manufacturer']['value'])
            self.assertIn('Plot 12',fields['manufacturer']['value'])
        self.assertNotIn('manufacturer',extract_fields('Marketed by: Example Labs'))

    def test_stamp_label_confusions_do_not_change_digits(self):
        fields=extract_fields('B.No.T25E637A MHG.MAY.2025EXP.ARR.2027')
        self.assertEqual(fields['mfg_date']['value'],'MFG.MAY.2025')
        self.assertEqual(fields['exp_date']['value'],'EXP.APR.2027')
        fields=extract_fields('T26B267B MFGFE8:2026 EXP.JAN.2028')
        self.assertEqual(fields['mfg_date']['value'],'MFGFEB:2026')
        self.assertNotIn('mfg_date',extract_fields('Mfg.LicNo.89/UA/SC/P-2016'))

    def test_inferred_batch_has_evidence_note(self):
        fields=extract_fields('B260158D M.R.P.76')
        self.assertEqual(fields['batch']['value'],'B260158D')
        self.assertTrue(fields['batch']['uncertain'])

    def test_crop_recovery_preserves_existing_date_and_records_evidence(self):
        rows=[{'text':'MFG M Y 20 6 EXP.APR.2028', 'source':'paddle_rotated',
               'box':[10,10,20,180], 'confidence':90}]
        readings=[('MFG.MAY 2026',.95,(0,0,100,15)),('EXP.APR.2029',.99,(0,20,100,35))]
        with patch('field_recovery._engine',return_value=object()),patch('ocr_paddle._run',return_value=readings):
            recovered,warnings=recover_fields(np.zeros((220,100,3),np.uint8),rows)
        self.assertFalse(warnings)
        self.assertEqual([r['recovered_field'] for r in recovered],['mfg_date'])
        self.assertEqual(recovered[0]['text'],'MFG.MAY 2026')
        self.assertIn('EXP.APR.2029',recovered[0]['crop_ocr_text'])
        self.assertEqual(rows[0]['text'],'MFG M Y 20 6 EXP.APR.2028')

    def test_recovered_manufacturer_does_not_absorb_neighboring_fields(self):
        text='Manufactured in India by Example Labs, Industrial Area\nUnrelated text below'
        rows=[{'text':text.splitlines()[0],'source':'paddle_field_recovery',
               'recovered_field':'manufacturer','box':[0,0,500,400]},
              {'text':'Unrelated text below','source':'paddle','box':[0,200,300,30]}]
        fields=extract_fields(text,rows)
        self.assertNotIn('Unrelated',fields['manufacturer']['value'])

    def test_empty_red_box_and_single_brand_line_are_not_warning_panels(self):
        im=np.full((300,600,3),255,np.uint8)
        cv2.rectangle(im,(30,50),(550,200),(0,0,180),-1)
        self.assertFalse(detect_warning_panel(im)['detected'])
        cv2.putText(im,'EXAMPLE BRAND',(60,130),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        self.assertFalse(detect_warning_panel(im)['detected'])

    def test_multirow_red_panel_reports_presence_only(self):
        im=np.full((300,600,3),255,np.uint8)
        cv2.rectangle(im,(30,50),(550,200),(0,0,180),-1)
        for y,t in [(90,'PRESCRIPTION WARNING'),(130,'TO BE SOLD BY RETAIL'),(170,'ONLY WITH PRESCRIPTION')]:
            cv2.putText(im,t,(50,y),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,0),2)
        result=detect_warning_panel(im)
        self.assertTrue(result['detected'])
        self.assertFalse(result['wording_verified'])


if __name__=='__main__':unittest.main()
