"""Mock Inference Provider for fast off-line testing."""
from typing import Any, Dict, List
from .base import BaseInferenceProvider


class MockInferenceProvider(BaseInferenceProvider):
    """Returns deterministic mock responses for unit testing without GPU requirements."""

    def __init__(self, default_response: str = "Mock assistant reply: I have received your support inquiry and noted your case details."):
        self.default_response = default_response

    def generate(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        if "paid" in last_user_msg.lower():
            return "Thank you for reaching out. Please click the 'Confirm Payment' button on your profile. If your payment is still not reflected after trying that, please provide your Remita RRR receipt number and payment date so we can investigate."

        if "ownership" in last_user_msg.lower():
            return "To assist with your change of ownership request, please confirm whether you are the buyer or the seller of the vehicle."

        return self.default_response
