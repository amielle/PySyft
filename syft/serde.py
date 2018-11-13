"""
This file exists to provide one common place for all serialization to occur
regardless of framework. As msgpack only supports basic types and binary formats
every type must be first be converted to one of these types. Thus, we've split our
functionality into three steps. When converting from a PySyft object (or collection
of objects) to an object to be sent over the wire (a message), those three steps
are (in order):

1. Simplify - converts PyTorch objects to simple Python objects (using pickle)
2. Serialize - converts Python objects to binary
3. Compress - compresses the binary (Now we're ready send!)

Inversely, when converting from a message sent over the wire back to a PySyft
object, the three steps are (in order):

1. Decompress - converts compressed binary back to decompressed binary
2. Deserialize - converts from binary to basic python objects
3. Detail - converts some basic python objects back to PyTorch objects (Tensors)

Furthermore, note that there is different simplification/serialization logic
for objects of different types. Thus, instead of using if/else logic, we have
global dictionarlies which contain functions and Python types as keys. For
simplification logic, this dictionary is called "simplifiers". The keys
are the types and values are the simplification logic. For example,
simplifiers[tuple] will return the function which knows how to simplify the
tuple type. The same is true for all other simplifier/detailer functions.

By default, we serialize using msgpack and compress using lz4.
"""

from typing import Collection
import pickle
import torch
import msgpack
import lz4

# High Level Public Functions (these are the ones you use)

def serialize(obj: object, compress=True) -> bin:

    simple_objects = _simplify(obj)
    binary = msgpack.dumps(simple_objects)

    if compress:
        return compress(binary)
    else:
        return binary


def deserialize(binary: bin, compressed=True) -> object:

    if compressed:
        binary = decompress(binary)

    simple_objects = msgpack.loads(binary)
    return _detail(simple_objects)


# Chosen Compression Algorithm

def compress(decompressed_input_bin: bin) -> bin:
    return lz4.frame.compress(decompressed_input_bin)


def decompress(compressed_input_bin: bin) -> bin:
    return lz4.frame.decompress(compressed_input_bin)


# Torch Tensor

def _simplify_torch_tensor(tensor):
    return pickle.dumps(tensor)


def _detail_torch_tensor(tensor):
    return pickle.loads(tensor)


# Collections (list, set, tuple, etc.)


def _simplify_collection(my_collection: Collection) -> Collection:
    """This function is designed to search a collection for any objects
    which may need to be simplified (i.e., torch tensors). It iterates
    through each object in the collection and calls _simplify on it. Finally,
    it returns the output collection as the same type as the input collection
    so that the consuming serialization step knows the correct type info.

    Args:
        Collection: a collection of python objects

    Returns:
        Collection: a collection of the same type as the input of simplified
            objects.

    """


    # Step 0: get collection type for later use and itialize empty list
    my_type = type(my_collection)
    pieces = list()

    # Step 1: serialize each part of the collection
    for part in my_collection:
        pieces.append(_simplify(part))

    # Step 2: convert back to original type and return serialization
    return my_type(pieces)


def _detail_collection(my_collection: Collection) -> Collection:

    pieces = list()

    # Step 1: deserialize each part of the collection
    for part in my_collection:
        pieces.append(_detail(part))

    return pieces


# High Level Simplification Router


def _simplify(obj: object) -> object:
    """This function takes an object as input and returns a simple
    Python object which is supported by the chosen serialization
    method (such as JSON or msgpack). The reason we have this function
    is that some objects are either NOT supported by high level (fast)
    serializers OR the high level serializers don't support the fastest
    form of serialization. For example, PyTorch tensors have custom pickle
    functionality thus its better to pre-serialize PyTorch tensors using
    pickle and then serialize the binary in with the rest of the message
    being sent.

    Args:
        obj: an object which may need to be simplified

    Returns:
        obj: an simple Python object which msgpack can serialize

    """

    try:
        # check to see if there is a simplifier
        # for this type. If there is, run return
        # the simplified object
        return simplifiers[type(obj)](obj)

    except KeyError:
        # if there is not a simplifier for this
        # object, then the object is already a
        # simple python object and we can just
        # return it

        return obj


simplifiers = {}

simplifiers[torch.Tensor] = _simplify_torch_tensor
simplifiers[tuple] = _simplify_collection
simplifiers[list] = _simplify_collection
simplifiers[set] = _simplify_collection


def _detail(obj: object) -> object:
    t = type(obj)
    if t in detailers:
        return detailers[t](obj)
    return obj


detailers = {}
detailers[tuple] = _detail_collection
detailers[list] = _detail_collection
detailers[bytes] = _detail_torch_tensor