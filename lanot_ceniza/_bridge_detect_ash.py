import runpy
import sys

def detect_ash_main():
    """
    Entry point for lanot-detect-ash CLI command.
    Arguments should be passed via command line, not as function parameters.
    """
    # Run detect_ash module from the lanot_ceniza package
    sys.exit(runpy.run_module('lanot_ceniza.detect_ash', run_name='__main__'))
