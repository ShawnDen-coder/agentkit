"""Custom NodeGraphQt node classes for the math/expression graph example.

6 node types under the ``math.nodes`` identifier:
  * NumberNode    — outputs a number (embedded QSpinBox)
  * StringNode    — outputs a string (embedded QLineEdit)
  * AddNode       — adds two inputs
  * SubtractNode  — subtracts input b from a
  * MultiplyNode  — multiplies two inputs
  * OutputNode    — displays its input value (debug sink)

NodeGraphQt API:
  * ``__identifier__`` — unique namespace (forms the node type id ``math.nodes.<Class>``)
  * ``NODE_NAME`` — default display name
  * ``add_input(name, multi_input=...)`` / ``add_output(name, multi_output=...)``
  * embedded widgets: ``add_spinbox`` / ``add_text_input`` / ``add_combo_menu`` / ``add_checkbox``
"""

from __future__ import annotations

from NodeGraphQt import BaseNode


__all__ = [
    "MATH_NODES",
    "AddNode",
    "MultiplyNode",
    "NumberNode",
    "OutputNode",
    "StringNode",
    "SubtractNode",
]


# Common identifier namespace for all math nodes.
_NODE_IDENTIFIER = "math.nodes"


class NumberNode(BaseNode):
    """A node that outputs a number (embedded QSpinBox widget)."""

    __identifier__ = _NODE_IDENTIFIER
    NODE_NAME = "Number"

    def __init__(self) -> None:
        """Create the value widget + output port."""
        super().__init__()
        # QSpinBox widget: widget_key, label, value, min, max, double
        self.add_spinbox("value", "Value", 0, -9999, 9999, double=True)
        self.add_output("value")

    def get_value(self) -> float:
        """Read the current spinbox value (float, since double=True)."""
        return float(self.get_property("value"))


class StringNode(BaseNode):
    """A node that outputs a string (embedded QLineEdit widget)."""

    __identifier__ = _NODE_IDENTIFIER
    NODE_NAME = "String"

    def __init__(self) -> None:
        """Create the text widget + output port."""
        super().__init__()
        self.add_text_input("value", "Text", tab="widgets")
        self.add_output("value")

    def get_value(self) -> str:
        """Read the current text value."""
        return str(self.get_property("value") or "")


class AddNode(BaseNode):
    """Adds two inputs (a + b)."""

    __identifier__ = _NODE_IDENTIFIER
    NODE_NAME = "Add"

    def __init__(self) -> None:
        """Create a, b inputs + result output."""
        super().__init__()
        self.add_input("a")
        self.add_input("b")
        self.add_output("result")


class SubtractNode(BaseNode):
    """Subtracts input b from a (a - b)."""

    __identifier__ = _NODE_IDENTIFIER
    NODE_NAME = "Subtract"

    def __init__(self) -> None:
        """Create a, b inputs + result output."""
        super().__init__()
        self.add_input("a")
        self.add_input("b")
        self.add_output("result")


class MultiplyNode(BaseNode):
    """Multiplies two inputs (a × b)."""

    __identifier__ = _NODE_IDENTIFIER
    NODE_NAME = "Multiply"

    def __init__(self) -> None:
        """Create a, b inputs + result output."""
        super().__init__()
        self.add_input("a")
        self.add_input("b")
        self.add_output("result")


class OutputNode(BaseNode):
    """A debug sink node that displays its input value."""

    __identifier__ = _NODE_IDENTIFIER
    NODE_NAME = "Output"

    def __init__(self) -> None:
        """Create a single input port (no outputs — it's a sink)."""
        super().__init__()
        self.add_input("value")


# Registry of all math node classes (for graph.register_nodes).
MATH_NODES: list[type[BaseNode]] = [
    NumberNode,
    StringNode,
    AddNode,
    SubtractNode,
    MultiplyNode,
    OutputNode,
]
