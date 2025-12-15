import runpy
import os

def detect_ash_main(**kwargs):
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'detect_ash.py')
    return runpy.run_path(script_path)
