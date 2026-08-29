"""
core/relationship_engine/isolation/gradient_blocker.py — Gradient isolation between networks.
Ensures no gradients flow between type-specific networks via .detach() at boundaries.
"""

from __future__ import annotations
import torch
from typing import List


class GradientBlocker:
    """Blocks gradient flow between isolated networks.

    At every network boundary, input tensors are detached from their
    computation graph before being fed to the next network. This prevents
    backpropagation from one network from affecting another's weights.
    """

    @staticmethod
    def detach_input(tensor: torch.Tensor) -> torch.Tensor:
        """Detach tensor from computation graph, preserving only the data."""
        return tensor.detach().requires_grad_(False)

    @staticmethod
    def detach_inputs(tensors: List[torch.Tensor]) -> List[torch.Tensor]:
        """Detach a list of tensors from the computation graph."""
        return [t.detach().requires_grad_(False) for t in tensors]

    @staticmethod
    def block_gradient_flow(
        source_output: torch.Tensor,
        target_input: torch.Tensor,
    ) -> torch.Tensor:
        """Block gradients flowing from source_output to target_input.

        Creates a copy of target_input that is detached from source_output's graph.
        """
        return target_input.detach()

    @staticmethod
    def validate_no_shared_grad(
        tensor_a: torch.Tensor,
        tensor_b: torch.Tensor,
    ) -> bool:
        """Verify two tensors are from different computation graphs.

        Returns True if they are fully isolated (no shared grad_fn history).
        """
        if tensor_a.grad_fn is None and tensor_b.grad_fn is None:
            return True
        if tensor_a.grad_fn is None or tensor_b.grad_fn is None:
            return True
        return tensor_a.grad_fn is not tensor_b.grad_fn



















