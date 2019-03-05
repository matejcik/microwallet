#!/usr/bin/env python3
"""The setup script."""

from setuptools import setup, find_packages

with open("README.rst") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst") as history_file:
    history = history_file.read()

requirements = [
    "Click>=7,<8",
    "trezor>=0.11.1",
    "attrs>=18.1.0",
    "websockets>=7.0",
    "construct>=2.9",
    "fastecdsa>=1.7",
]

setup(
    author='Jan "matejcik" Matějek',
    author_email="jan.matejek@satoshilabs.com",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    description="Bitcoin CLI wallet backed by Trezor hardware",
    entry_points={"console_scripts": ["microwallet=microwallet.cli:main"]},
    install_requires=requirements,
    license="GNU General Public License v3",
    long_description=readme + "\n\n" + history,
    include_package_data=True,
    keywords="microwallet",
    name="microwallet",
    packages=find_packages("src", include=["microwallet"]),
    package_dir={"": "src"},
    python_requires=">=3.6",
    url="https://github.com/trezor/microwallet",
    version="0.1.0",
    zip_safe=False,
)
