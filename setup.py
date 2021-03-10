from setuptools import find_packages, setup

version = '1.0.0'


def requirements(filename='requirements.txt'):
    with open(filename) as f:
        return f.readline()


setup(
    description='Python-notebook',
    include_package_data=True,
    install_requires=requirements(),
    name='python-notebook',
    version=version,
    extra_compile_args=['-Wno-cpp', '-Wno-unused-function', '-std=c99'],
)
