"""Apache inventory acquisition entry point for Tow Match Pro.

Uses the VDP-aware normalized adapter. Missing source values remain missing; parse/network
failures are logged by URL rather than silently converted into invented specifications.
"""
from adapters.apache_inventory import main
if __name__ == '__main__':
    main()
