"""Keep labscript_utils.excepthook from opening error windows during tests."""
import os

os.environ.setdefault('LABSCRIPT_DISABLE_GRAPHICAL_EXCEPTHOOK', '1')
