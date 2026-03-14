# Prepare for pyconfHyderadad talk - Jan 15th last. complete by 1st Jan.

[Talk plan](Talk%20plan%20322933924828808996d3e0ddb969641b.md)

- [ ]  Local model & RPA
- [ ]  Vision language models
- [ ]  small language models
- [ ]  llms on CPU

[Small Models, Big Impact: Why Your Next Production System Doesn’t Need a GPT](Small%20Models,%20Big%20Impact%20Why%20Your%20Next%20Production%20%202d0933924828807b9cd3dac6b2bb90b2.md)

https://research.google/blog/small-models-big-results-achieving-superior-intent-extraction-through-decomposition/

Topics - 

Offline models

---

[Prep plan for SLM talk](Prep%20plan%20for%20SLM%20talk%201086720323c049cdb4f2a6da48098371.md)

### Talk abstract (≈150–180 words)

**Small Language Models in Production: When Less Is More**

Most talks focus on ever-larger LLMs, but many real-world systems need something very different: predictable latency, strict cost ceilings, data residency, and the ability to run on boring CPUs. In this talk, we will look at how to use small language models (SLMs) to power production systems in Python, and why “less” is often exactly what you want.

We will cover how to choose and benchmark SLMs, what quantization actually buys you, and how to design architectures where a small local model does 90% of the work while a larger remote model is only used as a fallback. Using concrete examples and code, we will walk through an end-to-end SLM-powered service: from model selection and evaluation, to deployment on CPU-only infrastructure, to observability and failure modes in the wild.

You will leave with practical patterns, not hype: when to pick SLMs over LLMs, how to wire them into existing Python services, and where the sharp edges really are.

---

### Talk: Small Language Models in Production – When Less Is More

**Format:** 25 min talk + 5 min Q&A

1. **0–2 min — Setup and motivation**
    - Story of trying “just use a giant cloud LLM” and hitting cost / latency / data walls.
    - Frame question: where can small models do 80–90% of the work?
2. **2–6 min — What is a “small” language model and when is it enough?**
    - Define “small” (1B–8B params, single CPU box).
    - Use cases: routing / intent, tagging, structured extraction.
    - When you still need big models.
3. **6–12 min — Picking and taming SLMs (selection + quantization)**
    - Criteria: instruction-tuned, license, ecosystem.
    - Quantization: int8 / 4-bit on CPU, tradeoffs.
    - Simple Python benchmark: tokens/sec and basic accuracy vs big model.
4. **12–18 min — SLM-first, LLM-fallback architecture**
    - Diagram: Client → Gateway → Local SLM → optional Cloud LLM.
    - Fallback triggers: schema/regex failure, low-confidence outputs.
    - Python view: FastAPI SLM service + routing gateway.
5. **18–23 min — Demo (code-focused)**
    - Scenario: classify + extract fields from short ticket/email into JSON.
    - Show SLM latency on CPU and a hard example that triggers fallback.
    - Emphasize model interchangeability under a common interface.
6. **23–25 min — Sharp edges and checklist**
    - Failures: hallucinated structure, domain shift.
    - Mitigations: constrained outputs, retrieval, light finetuning.
    - Close with “Should I use a small model here?” checklist.

---

[https://www.foundrylocal.ai/models](https://www.foundrylocal.ai/models)

[talk-1.pdf](talk-1.pdf)

# Intro

![image.png](image.png)

what is slm - 

** https://freedium-mirror.cfd/https://ai.gopubby.com/slm-vs-llm-enterprise-2026-ab5f7d6b4f45

https://www.reddit.com/r/LocalLLaMA/comments/1kr2d1m/what_features_or_specifications_define_a_small/

https://www.bentoml.com/blog/the-best-open-source-small-language-models

[https://github.com/FairyFali/SLMs-Survey](https://github.com/FairyFali/SLMs-Survey)

Summary

### Talk Structure

- Title to be decided later
- Opening section will cover motivation and personal journey with efficient models over the past 10 years
- Focus on real-world applicability based on practical use cases

### Historical Context and Motivation

- Widespread adoption of small models began with TensorFlow Lite around 2016-2017
- Early work involved deploying models on mobile devices for logistics applications, using ImageNet-based models to classify boxes, furniture, and similar objects
- Past decade has seen significant improvements in both mobile resource architecture and machine learning/deep learning model development
- 2022-23 marked OpenAI's major expansion, leading many to adopt large models for chat completion, validation, parsing, and extraction tasks
- After a couple years of experience with these models, specialization tasks emerged including code generation, data parsing, and tool calling

### Current Challenge

- Most people default to large language models like GPT and Claude
- Due to time constraints or other factors, many don't explore small language model alternatives

### Talk Objectives

- Provide audience with understanding of what small language models are and where they can be applied
- Key takeaway: attendees should be able to download Ollama or similar tools, test models on their personal computers without requiring a GPU, and evaluate production viability

### Architecture Comparison Diagrams

**Current LLM Architecture:**

- Root node (application)
- Model selection layer (handles different use cases with specific prompts for tasks like parsing)
- Single large language model serving multiple use cases
- Inference layer
- Inference validation layer
- Action layer

**Proposed SLM Architecture:**

- Root node
- Model selection layer (based on specific use cases rather than just prompting)
- 4-5 example use cases with dedicated small language models (Phi, Gemma 3B, etc.) for each
- Each model has its own inference layer and validation layer
- Application layer

### Expected Audience Outcomes

- Understand what small language models are and their use cases
- Gain confidence to experiment with tools like Ollama
- Evaluate whether SLMs have production applicability for their current projects

Notes

Transcript

So we'll open the talk with a title, we'll decide later. The first introduction would be something like motivation. I've been exploring Models that are efficient and have a real world applicability in terms of the use cases that I've worked with over the last 10 years. The widespread use of small models, not language models, but then small models, I think started with TensorFlow Lite. probably, you know, 10 years before.

around 2016, 17. you know, for I mean, for my first startup. we did apply, you know, two or three models that are in logistic domains built on ImageNet for classifying, you know, like boxes, furniture, things like that. And this was in mobile devices of 2016. So over the last 10 years, we have come across Okay, gigantic improvement in terms of The mobile... resource architecture and as well as you know theAh.

architecture for model development and machine learning and deep learning as a whole. I've been on the journey for the last 10 years and I've seen first hand how things have starburst. 2022-23, OpenAI went big. And a lot of us started using opening ads as a general model for chat. completion, validations, parsing, extractions. Over the last couple of years after that, we see a lot of specialization tasks.

that comes out in our posts once we have some confidence working with the models for, you know, a year or two. And these tasks You know, something like... Code generation. Data passing. Duel Calling Plus such. So, there's a varied speciality of tasks that the model can do. What happens or what is happening at the moment is Most people Believe or you know stick to the large language models specifically GPT, cloud etc.

and Probably because of time constraints or their reads, they're not able to go to Small language models. So this talk would revolve around how we could or how you will have a view of what they are, and probably think about picking one of them and then running it on your personal computer. You don't need any GPU for this. So the takeaway that I think for you, for every one of you would be, Um, understand what they are, where they can be used and and and you will think that you're gonna go back and then just download olama or something normal model see how it's working and probably pick up you know this topic and then see if it is of any production use for anything that you're working So I also want to include a flow chart where there is You know Yarr, yarr.

Um... application you know architecture It starts with Different, you know, it starts with, let's say, and you'll be a call. or some top you know, root node and then after that in the flow chart you will have things like the first layer in that architecture in the tree is after the root node is that layer is the Action definition or not the action layer. It should be... Model selection layer. And then after the model selection layer, It should be You're, uh...

Large language model And then the Latin language model After that will be an inference layer. and inference validation layer. then there is an action that happens up you know on your application This is what we used today. or probably you will not have the model selection layer here. So it'll be root node. Uh-huh. or like model selection yes you need no selection because you have different use cases for different use cases that model model it's not model selection let's rename it as model Hmm.

splitting or something that specifically does something like you know for um parsing it will have a set of prompts to parse it and things like that and then it still uses the same you know one large large miniature model and after that there is an inference there's inference validation and there is an action so it'll be something like that But it'll be one root, multiple subroutes on the model selection layer.

And then there'll be again one child node to all of them that is an element and then one more child node inference layer, inference verification validation layer and then followed by the uh, action earlier The next slide on that regarding this would be using SLM swear. There will be the root node and then there will be model selection where instead of just prompting, it will be Um... For what use case?

SLMs will be used. We will have some like four or five examples. And then after that model selection layer, you will have you know model names like Phi, Pi, Gamma, gamma 3b so on small language models for each use case followed by You know every single one have their own inference and our validation. So inference Inference layer in for a validation layer and then the application layer
		

Summary

### Overview

- Speaker is planning to open their talk with audience polling questions
- Purpose: Understand audience composition and experience level to better tailor communication and content delivery
- Visual approach: Slide divided into five sections/columns, with four categories of questions

### Planned Audience Questions

Four show-of-hands questions to gauge audience experience with language models:

1. **Non-commercialized LLMs**: Experience with non-standard, non-commercialized large language models (excluding commercial models like ChatGPT, OpenAI, Gemini, Claude) 
2. **API Usage**: Experience using LLM APIs (such as OpenAI API) for completing tasks 
3. **Large Model Deployment**: Experience deploying large language models (50+ billion parameters) in the cloud and running inference  
4. **Small Language Models**: Experience with deploying or using small language models 

### Presentation Format

- Questions will be asked sequentially as show of hands
- Each category corresponds to a section on the opening slide
- The poll will help speaker adjust their presentation approach based on audience's technical background

Notes

Transcript

So at the start of the talk you will start the You will start by asking people for show fans. This is to understand what my audience are and how better I communicate what I'm going to deliver. First thing is, let's see how many people have used. Any of the non-commercialized large language models. So in the screen I have five divisions of my current screen, you know, slide where the first slide will talk about non-standard LLMs other than things like Gark.

Uh, OpenAI. Gemini, Claude, any of the commercialized models. So that is non-commercialized models that will be in the first slide. Second one is, the last, second part of the slide will be, second column in the s lide will be Using API So the API version of LLMs. Third one is someone who have deployed a large language model. Um... in cloud. So someone who has deployed more than 50 billion para model in cloud and have used them.

And finally we asked about how many people have used a small language model or have deployed them. So four I think. So first is non-standard, non-commercialized algorithms, OpenAI API. large language model but deployed one like llama, gamma and other things and then the small language models so four of them so first we ask the show of hands for non-commercialized algorithms second is how many people have deployed How many people have used OpenAI API? to the end of the task. Third one is how many people have deployed a large lagrange model and then have inference time for them. And then finally, how many people have small language model deployed it.
		

https://freedium-mirror.cfd/https://medium.com/@sparknp1/is-smaller-smarter-the-tiny-model-edge-ai-boom-6f28636e807e

# Examples - DEMO

Summary

### Demo Overview

- The demo will showcase code generation capabilities using SLMs (Small Language Models)
- A comparison link on code generation has been attached to the meeting notes for reference
- The approach will be to start with a minimal example to demonstrate that the model works for a given use case, avoiding unnecessary complexity initially

### Demo Setup

- Use Anti-Gravity platform
- Open the chart interface for modern traction

### Demo Content

**Simple Example:**

- Generate a website or create a code base for "ABC"
- This will serve as the basic demonstration of code generation capabilities

**Complex Examples:**

- Research and identify complex tasks that code generation models can handle
- Select a couple of these complex tasks to include in the demo
- Demonstrate how the model performs on these more challenging use cases

### Action Items

- [ ]  Open Anti-Gravity and set up the chart interface for modern traction
- [ ]  Prepare the simple demo: generate a website or code base for ABC
- [ ]  Search for complex code generation tasks that models can perform
- [ ]  Select and prepare a couple of complex task examples for the demo
- [ ]  Test how the model performs on the selected complex tasks

Notes

https://arxiv.org/html/2507.03160v2

Transcript

So, for examples of using SLMs, one of them is code generation. I'm attached I've attached a link to this note for a a certain comparison on code generation. I have one example to show there in the demo. open up anti-gravity and then open up the chart interface for modern traction and just I'll give a small example, minimal example, tell the audience that This is an example of using code generation, but you know you you're not I mean I'm restricting myself to be not complex here by giving a whole code base, but I'm just making sure that the model bug And it will work for a given use case.

I'm going to ask it to generate probably a website. or create a code base for ABC and also touch upon little complexity so find that complexity here so in code generation search for something like what is the complex task that the code generation model can do and then try to place a couple of them there and then see how the model performs and show it as a demo for code generation
		

I cant use this to my talk - [https://huggingface.co/blog/jjokah/small-language-model](https://huggingface.co/blog/jjokah/small-language-model) (year old and everything changes by then)

we work with 2 of the largest regulated domain - medical and banking - Tighter governance and compliance is the highest selling point

https://appinventiv.com/blog/small-language-models-in-enterprise-ai/

**SLM for RAG -** 

[https://medium.com/@adarshpandey.pandey355/using-small-language-models-slms-to-solve-real-world-problems-and-cut-costs-with-a-food-app-fc2d6909309d](https://medium.com/@adarshpandey.pandey355/using-small-language-models-slms-to-solve-real-world-problems-and-cut-costs-with-a-food-app-fc2d6909309d)

https://developers.googleblog.com/google-ai-edge-small-language-models-multimodality-rag-function-calling/

https://medium.com/@ronivaldo/small-models-for-rag-but-big-shift-why-the-future-of-ai-isnt-large-at-all-dc4e454ec0f5

https://thenewstack.io/build-cheaper-safer-auditable-ai-with-slms-and-rag/

**Document processing -**

https://hatchworks.com/blog/gen-ai/small-language-models/

https://kanerika.com/blogs/small-language-models/

**Tool selection / Calling**

https://arxiv.org/html/2510.07248v2

**Text to speech**

https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models

**Financial processing** 

[https://github.com/Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot)

https://arxiv.org/html/2601.01378v1

**SVLM -** 

https://huggingface.co/jinaai/jina-vlm

Computer use - 

https://huggingface.co/spaces/smolagents/computer-use-agent

# models

[https://www.semanticscholar.org/paper/Mercury%3A-Ultra-Fast-Language-Models-Based-on-Khanna-Kharbanda/6de03206638d7d43c4142a1dfc891849fa0ea696](https://www.semanticscholar.org/paper/Mercury%3A-Ultra-Fast-Language-Models-Based-on-Khanna-Kharbanda/6de03206638d7d43c4142a1dfc891849fa0ea696)

https://www.ziroh.com/model-listing

https://www.marktechpost.com/2026/01/06/liquid-ai-releases-lfm2-5-a-compact-ai-model-family-for-real-on-device-agents/

# Re training

https://arxiv.org/html/2601.03211v1

Future —

https://freedium-mirror.cfd/https://ai.gopubby.com/google-titans-neuroscience-ai-memory-explained-69b319f1f516

Mobile - 

https://allenai.org/blog/olmoe-app

reference - 

https://web.stanford.edu/~jurafsky/slp3/11.pdf