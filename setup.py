"""
Setup configuration for LANOT_ceniza project.
"""

from setuptools import setup

setup(
    name="lanot_ceniza",
    version="0.1.0",
    description="Detección de ceniza volcánica del Popocatépetl",
    author="LANOT",
    py_modules=["main"],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "matplotlib>=3.7.0",
        "pillow>=10.0.0",
        "pandas>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "lanot-ceniza=main:main",
        ],
    },
)
