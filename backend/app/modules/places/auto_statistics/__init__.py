"""Automatic Place statistics package.

Import concrete services from ``auto_statistics.service``. Keeping the package
initializer free of eager imports prevents a cycle when the Place repository
imports statistics domain records.
"""
