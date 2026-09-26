"""Local Qwen Inference Provider (Hugging Face Transformers / BitsAndBytes backend fallback)."""
from typing import Any, Dict, List, Optional
from .base import BaseInferenceProvider


class LocalQwenInferenceProvider(BaseInferenceProvider):
    """Loads and generates with Qwen directly inside the process (fallback mode)."""

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-4B-Instruct-2507",
        adapter_path: Optional[str] = None,
        use_4bit: bool = True,
    ):
        self.model_id = model_id
        self.adapter_path = adapter_path
        self.use_4bit = use_4bit
        self.tokenizer = None
        self.model = None
        self.device = None

    def load_backend(self):
        if self.tokenizer is not None and self.model is not None:
            return self.tokenizer, self.model

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            try:
                from peft import PeftModel
            except Exception:
                PeftModel = None
        except ImportError as err:
            raise ImportError("torch, transformers, and bitsandbytes are required for LocalQwenInferenceProvider.") from err

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_dtype = torch.bfloat16 if self.device == "cuda" and torch.cuda.get_device_capability()[0] >= 8 else torch.float16

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, use_fast=True, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        model_kwargs = {
            "trust_remote_code": True,
            "torch_dtype": compute_dtype,
            "low_cpu_mem_usage": True,
        }
        if self.device == "cuda":
            model_kwargs["device_map"] = "auto"
            if self.use_4bit:
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=compute_dtype,
                )
        else:
            model_kwargs["device_map"] = None

        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, **model_kwargs)
        if self.device != "cuda":
            self.model = self.model.to(self.device)

        if self.adapter_path and PeftModel is not None:
            self.model = PeftModel.from_pretrained(self.model, self.adapter_path)

        self.model.eval()
        return self.tokenizer, self.model

    def generate(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        import torch

        tokenizer_obj, model_obj = self.load_backend()
        if hasattr(tokenizer_obj, "apply_chat_template"):
            prompt = tokenizer_obj.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            prompt = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages) + "\nASSISTANT:"

        inputs = tokenizer_obj(prompt, return_tensors="pt")
        input_device = getattr(model_obj, "device", next(model_obj.parameters()).device)
        inputs = {k: v.to(input_device) for k, v in inputs.items()}

        max_new_tokens = kwargs.get("max_new_tokens", 512)
        temperature = kwargs.get("temperature", 0.2)
        top_p = kwargs.get("top_p", 0.9)

        gen_kwargs = {
            "max_new_tokens": max_new_tokens,
            "do_sample": temperature > 0,
            "pad_token_id": tokenizer_obj.eos_token_id,
        }
        if temperature > 0:
            gen_kwargs.update({"temperature": temperature, "top_p": top_p})

        with torch.no_grad():
            generated = model_obj.generate(**inputs, **gen_kwargs)

        new_tokens = generated[0][inputs["input_ids"].shape[-1]:]
        return tokenizer_obj.decode(new_tokens, skip_special_tokens=True).strip()
