import os
import sys

import torch
from torch.testing import FileCheck
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

# Make the helper files in test/ importable
pytorch_test_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(pytorch_test_dir)
from torch.testing._internal.jit_utils import JitTestCase

if __name__ == '__main__':
    raise RuntimeError("This test file is not meant to be run directly, use:\n\n"
                       "\tpython test/test_jit.py TESTNAME\n\n"
                       "instead.")

class TestUnion(JitTestCase):
    """
    This class tests the functionality of `Union`.

    Note: It's important to be able to refine the type of a `Union` to
    one of its internal types. Currently, there are differences in the
    way Python expects `isinstance` checks and the way TorchScript
    expects `isinstance` checks. This means that we can't use
    `checkScript` in our test cases because either the eager mode or the
    script mode wouldn't run! So, some test cases have separate but
    equivalent functions to emulate `checkScript`.
    """

    def test_union_with_scalar_values(self):
        def fn(x: Union[int, float]) -> str:
            return "foo"

        self.checkScript(fn, (1,))
        self.checkScript(fn, (1.0,))

        scripted = torch.jit.script(fn)

        with self.assertRaisesRegex(RuntimeError, "Expected a member of"
                                    r" Union\[float, int\] but "
                                    "instead found type str"):
            scripted("1")

    def test_union_with_collections(self):
        def fn(x: Union[Dict[str, int], List[int]]) -> str:
            return "foo"

        self.checkScript(fn, ({"foo": 1, "bar": 2, "baz": 3},))
        self.checkScript(fn, ([1, 2, 3],))

        scripted = torch.jit.script(fn)

        with self.assertRaisesRegex(RuntimeError, "Expected a member of"
                                    r" Union\[List\[int\], Dict\[str, "
                                    r"int\]\] but instead found type "
                                    r"Dict\[str, str\]"):
            scripted({"foo": "bar", "baz": "qux"})

        with self.assertRaisesRegex(RuntimeError, "Expected a member of"
                                    r" Union\[List\[int\], Dict\[str, "
                                    r"int\]\] but instead found type "
                                    r"List\[str\]"):
            scripted(["foo", "bar", "baz"])

        with self.assertRaisesRegex(RuntimeError, "Expected a member of"
                                    r" Union\[List\[int\], Dict\[str, "
                                    r"int\]\] but instead found type "
                                    "str"):
            scripted("1")

    def test_union_with_enum(self):

        global Color

        class Color(Enum):
            RED = 1
            GREEN = 2

        def fn(x: Union[str, Color]) -> str:
            return "foo"

        self.checkScript(fn, (Color.RED,))
        self.checkScript(fn, ("red",))

        scripted = torch.jit.script(fn)

        with self.assertRaisesRegex(RuntimeError, "Expected a member of"
                                    r" Union\[__torch__.jit.test_union."
                                    r"Color, str\] but instead found "
                                    "type int"):
            scripted(1)

    def test_union_in_class_constructor(self):

        @torch.jit.script
        class A(object):    # noqa B903
            def __init__(self, x: Union[int, str]) -> None:
                self.x = x

        def fn(x: Union[str, int]) -> A:
            return A(x)

        self.assertEqual(fn("foo").x, "foo")
        self.assertEqual(fn(1).x, 1)

        scripted = torch.jit.script(fn)

        with self.assertRaisesRegex(RuntimeError, "Expected a member of"
                                    r" Union\[int, str\] but instead "
                                    r"found type List\[str\]"):
            scripted(["foo", "bar", "baz"])

    def test_union_return_type(self):
        def fn(x: int) -> Union[int, str]:
            return "foo"

        self.checkScript(fn, (1,))

    def test_union_as_annotation(self):
        def fn() -> Union[int, str]:
            x: Union[int, str] = "foo"
            return x

        self.checkScript(fn, ())

    def test_union_as_annotation_in_typed_container(self):
        def fn() -> None:
            l: List[Union[int, str]] = []
            u1: Union[int, str] = "foo"
            u2: Union[int, str] = 1
            l.append(u1)
            l.append(u2)

        self.checkScript(fn, ())

    def test_union_as_annotation_py2(self):
        def fn():
            # type: () -> Union[int, str]
            x: Union[int, str] = "foo"
            return x

        self.checkScript(fn, ())

    def test_union_as_internal_tuple_type(self):
        def fn():
            t: Tuple[Union[int, str], Union[int, str]] = (1, "foo")
            return t

        self.checkScript(fn, ())

    def test_union_variable_can_be_reassigned(self):
        @torch.jit.script
        def aux1(i: int):
            return int(i ** 2)

        @torch.jit.script
        def aux2(s: str):
            return s + s

        def fn() -> Union[int, str]:
            x: Union[int, str] = "foo"
            i: int = 1
            x = i
            y: int = aux1(x)
            z: str = aux2(str(y))
            x = z
            return x

        self.checkScript(fn, ())

    def test_union_does_not_replace_existing_annotated_type(self):
        def fn():
            x: List[int] = [1, 2, 3]
            x.append("foo")
            return x

        with self.assertRaisesRegex(RuntimeError, "Could not match type str"):
            scripted = torch.jit.script(fn)
            scripted()

    def test_union_does_not_replace_existing_annotated_type_union(self):
        def fn():
            x: List[Union[int, str]] = [1, "foo", 3]
            x.append(2.0)
            return x

        with self.assertRaisesRegex(RuntimeError, "Could not match type float"):
            scripted = torch.jit.script(fn)
            scripted()

    def test_union_does_not_replace_existing_annotated_type_empty_container(self):
        def fn():
            x: List[int] = []
            x.append("foo")
            return x

        with self.assertRaisesRegex(RuntimeError, "Could not match type str"):
            scripted = torch.jit.script(fn)
            scripted()

    def test_unions_of_unions_are_flattened(self):
        @torch.jit.script
        def fn(x: Union[Union[int, str], float]) -> str:
            return "foo"

        s = fn.graph

        FileCheck().check("x : Union[float, int, str]")    \
                   .run(s)

    def test_unions_of_a_single_argument_vanish(self):
        @torch.jit.script
        def fn(x: Union[int]) -> str:
            return "foo"

        s = fn.graph

        FileCheck().check("x : int")    \
                   .run(s)

    def test_union_redundant_arguments_are_skipped(self):
        @torch.jit.script
        def fn(x: Union[int, str, int]) -> str:
            return "foo"

        s = fn.graph

        FileCheck().check("x : Union[int, str]")    \
                   .run(s)

    def test_union_redundant_arguments_are_skipped_optional(self):
        @torch.jit.script
        def fn(x: Union[int, Optional[float], Optional[int]]) -> str:
            return "foo"

        s = fn.graph

        FileCheck().check("x : Union[float, int, NoneType]")    \
                   .run(s)

    def test_union_redundant_arguments_are_skipped_subtyping(self):
        @torch.jit.script
        def fn(x: Union[str, Tuple[Optional[int], int], Tuple[int, int]]) -> str:
            return "foo"

        s = fn.graph

        FileCheck().check("x : Union[(int?, int), str]")    \
                   .run(s)

    def test_union_redundant_arguments_are_skipped_container(self):
        @torch.jit.script
        def fn(x: Union[List[str], List[float], List[str]]) -> str:
            return "foo"

        s = fn.graph

        FileCheck().check("x : Union[float[], str[]]")     \
                   .run(s)

    def test_union_argument_order_is_ignored(self):
        @torch.jit.script
        def fn1(x: Union[int, str]) -> str:
            return "foo"

        @torch.jit.script
        def fn2(x: Union[str, int]) -> str:
            return "foo"

        for s in (fn1.graph, fn2.graph):
            FileCheck().check("x : Union[int, str]")     \
                .run(s)

    def test_union_argument_order_is_ignored_container(self):
        @torch.jit.script
        def fn1(x: Union[List[str], List[int]]) -> str:
            return "foo"

        @torch.jit.script
        def fn2(x: Union[List[int], List[str]]) -> str:
            return "foo"

        for s in (fn1.graph, fn2.graph):
            FileCheck().check("x : Union[int[], str[]]")     \
                .run(s)

    def test_union_T_None_is_equivalent_to_optional_T(self):
        @torch.jit.script
        def inner(x: Union[int, None]) -> int:
            if x is not None:
                return x
            else:
                return 5

        @torch.jit.script
        def fn1() -> int:
            a: Optional[int] = 5
            b: Optional[int] = None
            a_ = inner(a)
            b_ = inner(b)
            return a_ + b_

        self.assertEqual(fn1(), 10)

        @torch.jit.script
        def inner2(x: Optional[int]) -> int:
            if x is not None:
                return x
            else:
                return 5

        @torch.jit.script
        def fn2() -> int:
            a: Union[int, None] = 5
            b: Union[int, None] = None
            a_ = inner(a)
            b_ = inner(b)
            return a_ + b_

        self.assertEqual(fn2(), 10)

    def test_union_subclasses_larger_union(self):
        def fn() -> Union[int, str, torch.Tensor]:
            x: Union[int, str] = "foo"
            return x

        self.checkScript(fn, ())

    # TODO: We would like to eventually support this. The issue is being
    # tracked at https://github.com/pytorch/pytorch/issues/58167
    def test_union_as_dict_key(self):
        def fn():
            x: Dict[Union[int, str], str] = {}
            x["foo"] = "bar"
            x[1] = 2
            return x[1]

        with self.assertRaisesRegex(RuntimeError, "only int, float, "
                                    "complex, Tensor and string keys "
                                    "are supported"):
            torch.jit.script(fn)

    def test_union_as_dict_value(self):
        def fn():
            x: Dict[str, Union[int, str]] = {}
            x["foo"] = "bar"
            x["baz"] = 2
            return x["baz"]

        self.checkScript(fn, ())

    def test_union_module_with_union_instance_variable(self):
        class M(torch.nn.Module):

            x: Union[int, str]

            def __init__(self, x: Union[int, str]):
                super().__init__()
                self.x: Union[int, str] = x

            def forward(self, y: Union[int, str]):
                self.x = y
                return self.x

        self.checkModule(M(2,), (1,))
        self.checkModule(M("bar"), ("foo",))

    def test_union_module_with_union_class_variable(self):
        class M(torch.nn.Module):
            x: Union[int, str] = "foo"

            def __init__(self, y: int):
                super().__init__()
                x = y

            def forward(self, z: str):
                x = z
                return x

        self.checkModule(M(1), ("foo",))
