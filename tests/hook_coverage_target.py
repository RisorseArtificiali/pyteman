"""Target module for the import hook coverage tests.

A standalone module, not part of a package, with one patchable function.
The tests use it through every import form the matrix covers.
"""


def greet(name):
    return f"hello {name}"
