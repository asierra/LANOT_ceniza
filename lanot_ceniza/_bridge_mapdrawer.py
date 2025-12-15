import runpy
import sys

def draw_map_main():
    """
    Entry point for lanot-draw-map CLI command.
    Arguments should be passed via command line, not as function parameters.
    """
    # Run mapdrawer module from the lanot_ceniza package
    sys.exit(runpy.run_module('lanot_ceniza.mapdrawer', run_name='__main__'))
