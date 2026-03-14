# Foundations of SLMs and quantization (2–3 days, part-time)

- What makes a model "small" (1B–8B params, RAM needs, context length).
- Quantization basics: int8 vs 4-bit, GGUF, how it affects latency and quality.
- CPU vs GPU inference tradeoffs.
- Deliverable: shortlist of 3–5 candidate models with notes (license, context, quantization support).

---

Here are some helpful online resources to learn about SLMs and quantization:

**Understanding Small Language Models:**

- [Hugging Face's Model Hub documentation](https://huggingface.co/docs/hub/models) - has practical guides on model sizes, parameter counts, and memory requirements
- [Sebastian Raschka's blog posts on LLM fundamentals](https://sebastianraschka.com/blog/) - covers the basics of what makes models "small" vs "large"

**Quantization Techniques:**

- [Hugging Face's Quantization guide](https://huggingface.co/docs/optimum/concept_guides/quantization) - comprehensive overview of int8, 4-bit quantization, and GPTQ/GGUF formats
- [llama.cpp documentation](https://github.com/ggerganov/llama.cpp) - excellent resource for understanding GGUF format specifically
- [Google's "Introduction to Weight Quantization" whitepaper](https://arxiv.org/abs/2106.08295) - covers the theory behind quantization and quality tradeoffs

**CPU vs GPU Inference:**

- [ONNX Runtime documentation](https://onnxruntime.ai/docs/performance/) - explains CPU optimization techniques
- [PyTorch performance tuning guide](https://pytorch.org/tutorials/recipes/recipes/tuning_guide.html) - covers CPU and GPU inference patterns
- [Papers with Code's "Efficient Inference" section](https://paperswithcode.com/task/efficient-inference) - academic papers with practical implementations

**Model Selection:**

- [Hugging Face Open LLM Leaderboard](https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard) - compare models by size, performance, and license
- [LMSys Chatbot Arena](https://lmsys.org/blog/2023-05-03-arena/) - real-world benchmarks for smaller models
- [GGUF model repositories on Hugging Face (TheBloke's collection)](https://huggingface.co/TheBloke) - pre-quantized models with detailed specs