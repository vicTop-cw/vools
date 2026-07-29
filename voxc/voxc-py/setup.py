from setuptools import setup, find_packages

setup(
    name="voxc-py",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "lark>=1.0",
    ],
    entry_points={
        "console_scripts": [
            "voxc-py=voxc.__main__:main",
        ],
    },
)