import runpy
import os

def draw_map_main():
    """
    Entry point for lanot-draw-map CLI command.
    Arguments should be passed via command line, not as function parameters.
    """
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mapdrawer.py')
    return runpy.run_path(script_path, run_name='__main__')
