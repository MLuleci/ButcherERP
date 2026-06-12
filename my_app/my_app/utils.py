import base64
from io import BytesIO

import qrcode


def get_qr_base64(value):
	buf = BytesIO()
	qrcode.make(value, error_correction=qrcode.constants.ERROR_CORRECT_M).save(buf, format="PNG")
	return base64.b64encode(buf.getvalue()).decode()
