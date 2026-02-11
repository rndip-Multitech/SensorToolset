"""
Stub for IDE import resolution. Loads the real implementation from static/py/app_paths.py.
"""

import importlib.util
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_py_dir = os.path.join(_here, "static", "py")
if _py_dir not in sys.path:
    sys.path.insert(0, _py_dir)

_real_path = os.path.join(_py_dir, "app_paths.py")
_spec = importlib.util.spec_from_file_location("_app_paths_impl", _real_path)
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

get_app_root = _impl.get_app_root
get_custom_decoders_dir = _impl.get_custom_decoders_dir
get_data_root = _impl.get_data_root
get_config_dir = _impl.get_config_dir
get_network_dashboard_py_dir = _impl.get_network_dashboard_py_dir
get_uplink_cache_dir = _impl.get_uplink_cache_dir
is_frozen = _impl.is_frozen
