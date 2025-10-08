# -*- coding: utf-8 -*-
"""
Runtime hook for PyInstaller
Ensures that local modules can be imported from the bundle
"""

import sys
import os

# Add the application directory to sys.path to make local modules importable
if hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    sys.path.insert(0, sys._MEIPASS)
    
    # Also ensure the modules are importable
    import importlib.util
    
    # List of local modules that need to be available
    local_modules = ['updater', 'external_updater', 'config']
    
    for module_name in local_modules:
        module_path = os.path.join(sys._MEIPASS, f'{module_name}.py')
        if os.path.exists(module_path):
            # Load the module from the file
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
