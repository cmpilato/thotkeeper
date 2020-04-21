#!/usr/bin/env python3

from setuptools import setup, find_packages
from thotkeeper import __version__ as tk_version

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='thotkeeper',
    version=tk_version,
    author='C. Michael Pilato',
    author_email='cmpilato@red-bean.com',
    description='Cross-platform personal daily journaling',
    long_description=long_description,
    long_description_content_type='text/markdown',
    keywords='journaling',
    url='https://github.com/cmpilato/thotkeeper',
    packages=find_packages(),
    package_data={
        'thotkeeper': ['thotkeeper/*.xrc'],
    },
    entry_points={
        'console_scripts': [
            'thotkeeper = thotkeeper:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: BSD-2 License',
        'Operating System :: OS Independent',
    ],
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    python_requires='>=3.4',
)
