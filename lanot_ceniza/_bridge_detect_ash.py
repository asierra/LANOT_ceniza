import runpy
import os

def detect_ash_main():
    """
    Entry point for lanot-detect-ash CLI command.
    Arguments should be passed via command line, not as function parameters.
    """
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'detect_ash.py')
    return runpy.run_path(script_path, run_name='__main__')
