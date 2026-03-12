"""
CTF Detector Registry Tests

Bug Ticket: Bug — register_detector decorator erases subclass type.
            The inner decorator is typed as:
                def decorator(cls: Type[BaseDetector]) -> Type[BaseDetector]
            which causes Pylance to lose the concrete subclass (e.g. ToolCallDetector)
            after decoration, making subclass-only attributes inaccessible to the
            type checker.

Acceptance Criteria (from ticket):
- After applying @register_detector, the returned class is identical to the input class
  (REG-DEC-001 through REG-DEC-002)
- The decorator's return-type annotation uses a TypeVar (not a bare Type[BaseDetector])
  so Pylance can preserve the concrete subclass type through decoration
  (REG-DEC-003)

Production Impact
=================
The registry is the sole mechanism by which detector classes are discovered and
instantiated at startup. A broken decorator silently corrupts the class hierarchy:

- REG-DEC-001/002  If decoration returns a different class object, isinstance checks
                   and attribute access on live detector instances fail with
                   AttributeError at runtime — the detector crashes on the first
                   real event, leaving every subsequent event unchecked.
- REG-DEC-003      If the TypeVar annotation is absent, Pylance erases concrete
                   subclass types across the entire codebase, suppressing type
                   errors that would otherwise catch misconfigured detectors
                   before deployment.
"""

import typing

import pytest

from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.base import BaseDetector


class TestRegisterDetectorPreservesClassIdentity:

    @pytest.mark.unit
    def test_reg_dec_001_decorated_class_is_identical_to_original(self):
        """REG-DEC-001: @register_detector must return the exact same class object.

        Title: REG-DEC-001: Decorated class identity is preserved
        Description: The register_detector decorator must be transparent — it
                     registers the class in the internal registry and returns
                     the same class unchanged so that isinstance checks and
                     direct attribute access continue to work.

        Steps:
            1. Define a minimal BaseDetector subclass with a subclass-only method
            2. Apply register_detector to it
            3. Compare the result to the original class

        Expected Results:
            The decorated result is the same object as the original class (is check passes)

        Impact: If the decorator wraps the class in a new type instead of
                returning the original, every isinstance(detector, SomeDetector)
                check in the pipeline fails. Detectors that pass startup
                registration are silently orphaned: the registry holds a
                different class object than the one the rest of the codebase
                references, so create_detector() produces instances that no
                existing code can type-check or call safely.
        """
        class _FakeDetector(BaseDetector):
            def get_relevant_event_types(self) -> list[str]:
                return []

            async def check_event(self, event, db):  # type: ignore[override]
                pass

            def subclass_only(self) -> str:
                return "only_in_subclass"

        decorated = register_detector("_test_identity")(_FakeDetector)
        assert decorated is _FakeDetector, (
            "REG-DEC-001: register_detector must return the original class unchanged."
        )

    @pytest.mark.unit
    def test_reg_dec_002_subclass_only_method_accessible_on_instance(self):
        """REG-DEC-002: Instances of a decorated subclass still expose subclass-only methods.

        Title: REG-DEC-002: Subclass-only attributes are accessible after decoration
        Description: A method defined only on the subclass (not on BaseDetector)
                     must remain callable on instances created from the decorated class.

        Steps:
            1. Decorate a subclass that has a subclass-only method
            2. Instantiate the decorated class
            3. Call the subclass-only method

        Expected Results:
            The method is reachable and returns the expected value

        Impact: If decoration wraps the class and drops subclass methods,
                calling any detector-specific helper (e.g. a threshold lookup
                or config accessor defined only on InvoiceThresholdBypassDetector)
                raises AttributeError at the first event processed. The detector
                silently exits its coroutine, making every attack on that check
                invisible from that point forward until the service restarts.
        """
        class _FakeDetector2(BaseDetector):
            def get_relevant_event_types(self) -> list[str]:
                return []

            async def check_event(self, event, db):  # type: ignore[override]
                pass

            def subclass_only(self) -> str:
                return "hello_from_subclass"

        Decorated = register_detector("_test_method_access")(_FakeDetector2)
        instance = Decorated(challenge_id="x", config={})
        assert instance.subclass_only() == "hello_from_subclass"  # type: ignore[attr-defined]


class TestRegisterDetectorTypeAnnotation:

    @pytest.mark.unit
    def test_reg_dec_003_return_annotation_uses_typevar_not_base_detector(self):
        """REG-DEC-003: The inner decorator's return annotation must use a TypeVar.

        Title: REG-DEC-003: Decorator uses TypeVar so Pylance preserves concrete subclass type
        Description: When the decorator is typed as:
                         def decorator(cls: Type[BaseDetector]) -> Type[BaseDetector]
                     Pylance erases the concrete subclass type after decoration.
                     The fix is to use a TypeVar T (bound=BaseDetector) so that
                     Pylance infers the return as Type[T] matching the input.

        Steps:
            1. Call register_detector("x") to obtain the inner decorator function
            2. Inspect its 'return' annotation via __annotations__
            3. Extract the single type argument from the Type[...] wrapper
            4. Assert that argument is a TypeVar, not BaseDetector itself

        Expected Results:
            typing.get_args(return_annotation)[0] is a TypeVar instance
            (fails before fix when it is BaseDetector; passes after fix)

        Impact: Without the TypeVar the type checker infers every decorated
                class as BaseDetector, not its concrete subclass. This suppresses
                type errors throughout the codebase: misconfigured detectors
                with wrong threshold types, missing required config fields, or
                typos in attribute names all pass static analysis silently.
                Bugs that should be caught during CI reach production as runtime
                crashes on the first live event.
        """
        inner_decorator = register_detector("_test_typevar")
        return_ann = inner_decorator.__annotations__.get("return")

        assert return_ann is not None, (
            "REG-DEC-003: inner decorator must have a 'return' type annotation."
        )

        args = typing.get_args(return_ann)
        assert len(args) == 1, (
            f"REG-DEC-003: expected Type[...] with one argument, got {return_ann!r}."
        )

        type_arg = args[0]
        assert isinstance(type_arg, typing.TypeVar), (
            f"REG-DEC-003: return annotation is Type[{type_arg!r}] — must be a TypeVar "
            f"(e.g. T = TypeVar('T', bound=BaseDetector)), not the bare BaseDetector class. "
            f"Fix: change decorator signature to "
            f"'def decorator(cls: Type[T]) -> Type[T]' using a TypeVar."
        )
