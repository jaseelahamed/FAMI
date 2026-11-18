"""Re-read ambiguous quantities from pixels; never substitute digits on faith."""
import re

import cv2


_QUANTITY = re.compile(r"(?<!\w)([0-9OoSs]+(?:\.[0-9OoSs]+)?)\s*(mg|mcg|µg|g|ml|iu)(?!\w)", re.I)


def recover_quantities(image, rows, backend):
    """Confirm O/0 and S/5 confusions with high-confidence crop OCR.

    Keep Paddle's text and geometry except for confirmed quantity tokens. Original
    text and the confirming crop reading remain attached for audit. Unconfirmed
    tokens are untouched and continue to require review in field validation.
    """
    warnings = []
    for row in rows:
        matches = list(_QUANTITY.finditer(row['text']))
        ambiguous = [m for m in matches if re.search('[OoSs]', m[1])]
        if not ambiguous or row['source'] != 'paddle':
            continue
        expected = [(m[1].translate(str.maketrans('OoSs', '0055')), m[2].lower()) for m in matches]
        x, y, w, h = map(round, row['box'])
        crop = image[max(0, y-5):min(image.shape[0], y+h+5),
                     max(0, x-5):min(image.shape[1], x+w+5)]
        if not crop.size:
            continue
        try:
            for scale, binary in ((3, False), (4, True)):
                enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                if binary:
                    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
                    enlarged = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
                data = backend.image_to_data(enlarged, config='--psm 7',
                                             output_type=backend.Output.DICT, timeout=10)
                tokens = [(t.strip(), float(c)) for t, c in zip(data['text'], data['conf']) if t.strip()]
                reading = ' '.join(t for t, _ in tokens)
                confirmed = list(_QUANTITY.finditer(reading))
                if [(m[1], m[2].lower()) for m in confirmed] != expected:
                    continue
                spans, offset = [], 0
                for token, confidence in tokens:
                    spans.append((offset, offset+len(token), confidence))
                    offset += len(token)+1
                confidences = [min(c for start, end, c in spans if start < m.end() and end > m.start()) for m in confirmed]
                if any(c < 75 for c in confidences):
                    continue
                row['original_text'] = row['text']
                row['quantity_corrections'] = []
                for index in reversed(range(len(matches))):
                    match = matches[index]
                    if match not in ambiguous:
                        continue
                    replacement = expected[index][0]
                    row['text'] = row['text'][:match.start(1)]+replacement+row['text'][match.end(1):]
                    row['quantity_corrections'].append({'original': match[0],
                        'confirmed': confirmed[index][0], 'confidence': confidences[index],
                        'source': 'tesseract_quantity_crop', 'crop_reading': reading})
                row['confidence'] = min(row['confidence'], *confidences)
                break
        except Exception as exc:
            warnings.append(f'Quantity verification unavailable; original OCR retained: {exc}')
    return warnings
