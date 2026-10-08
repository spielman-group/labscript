"""Keep labscript_utils.excepthook from opening error windows during tests."""
import os

os.environ.setdefault('LABSCRIPT_NO_ERROR_DIALOG', '1')
