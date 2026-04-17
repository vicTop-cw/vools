"""
vools 包安装配置
"""

from setuptools import setup, find_packages
import os

# 读取 README.md 作为长描述
with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

# 读取版本信息
with open(os.path.join('vools', '__init__.py'), 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip('"')
            break

setup(
    name="vools",
    version=version,
    author="Victor",
    author_email="victor@example.com",
    description="Python 函数式编程工具集",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/victor/vools",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'vools': ['config.template.py'],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Functional Programming",
    ],
    python_requires=">=3.6",
    install_requires=[
        "wrapt==1.10.11",
        "pandas>=0.22.0",
        "numpy>=1.14.0",
    ],
    extras_require={
        "dev": [
            "pytest==3.3.2",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort==4.2.15",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "vools=vools.__main__:main",
        ],
    },
)
