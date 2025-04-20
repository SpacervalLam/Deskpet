from setuptools import setup, find_packages

setup(
    name="Desktop_pet_Project",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'PyQt5',
        'PyOpenGL',
        'keyboard',
    ],
    author="SpacervalLam",
    author_email="spacervallam@gmail.com",
    description="A project integrates Live2D with PyQt5 for GUI and OpenGL rendering.",
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
