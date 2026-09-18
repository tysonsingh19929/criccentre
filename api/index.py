import os
import sys

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.dashboard_server import DashboardHTTPHandler

class handler(DashboardHTTPHandler):
    def __init__(self, *args, **kwargs):
        output_dir = os.path.join(ROOT_DIR, 'output')
        super().__init__(*args, directory=output_dir, **kwargs)
