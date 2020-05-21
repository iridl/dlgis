""" dlgis package configuration
"""
from typing import Any, Dict
import setuptools  # type: ignore

about: Dict[Any, Any] = {}
with open("dlgis/__about__.py") as f:
    exec(f.read(), about)

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name=about["name"],
    version=about["version"],
    author=about["author"],
    author_email=about["email"],
    description="Data Library GIS datasets",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://bitbucket.org/iridl/dlgis",
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">= 3.7",
    install_requires=[
        "click == 7.1.*",
        "pyshp == 2.1.*",
        "gdal == 3.0.*",  # conda package
        # requires shp2pgsql 2.5.*, psql, grep and sed  binaries
    ],
    scripts=["dlgis_import", "dlgis_export"],
    project_urls={"Bug Reports": "https://bitbucket.org/iridl/dlgis/issues"},
)
